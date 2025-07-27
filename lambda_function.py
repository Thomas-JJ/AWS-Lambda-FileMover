# lambda_function.py - Enhanced with Priority & Flexible Pattern Matching
import json
import boto3
import urllib.parse
import os
import re
from datetime import datetime

# Global variables for caching
cached_config = None
config_last_modified = None

def lambda_handler(event, context):
    s3_client = boto3.client('s3')
    
    # Load routing configuration
    routing_rules = load_routing_config(s3_client)
    
    processed_files = []
    errors = []
    
    for record in event['Records']:
        source_bucket = record['s3']['bucket']['name']
        source_key = urllib.parse.unquote_plus(record['s3']['object']['key'], encoding='utf-8')
        
        # Skip config file itself
        config_key = os.environ.get('CONFIG_FILE_KEY', 'config/routing-rules.json')
        if source_key == config_key:
            print("Config file updated - cache will refresh on next invocation")
            continue
            
        print(f"Processing: s3://{source_bucket}/{source_key}")
        
        # Find best matching rule by priority
        destination_info = find_best_destination(source_key, routing_rules)
        
        if destination_info:
            result = process_file(s3_client, source_bucket, source_key, destination_info)
            if result['success']:
                processed_files.append(result)
            else:
                errors.append(result)
        else:
            print(f"No routing rule found for: {source_key}")
            print("File will be ignored - no default processing")
            # File is ignored - no error added, just logged
    
    return {
        'statusCode': 200 if len(errors) == 0 else 207,
        'body': json.dumps({
            'processed_files': len(processed_files),
            'errors': len(errors),
            'details': {
                'successful': processed_files,
                'failed': errors
            }
        })
    }

def load_routing_config(s3_client):
    """Load routing configuration from S3 with caching"""
    global cached_config, config_last_modified
    
    config_bucket = os.environ.get('CONFIG_BUCKET', '')
    config_key = os.environ.get('CONFIG_FILE_KEY', 'config/routing-rules.json')
    
    try:
        # Check if config has been modified
        head_response = s3_client.head_object(Bucket=config_bucket, Key=config_key)
        last_modified = head_response['LastModified']
        
        # Use cached config if still current
        if cached_config and config_last_modified and last_modified <= config_last_modified:
            print("Using cached routing configuration")
            return cached_config
        
        # Load fresh config
        print(f"Loading routing config from s3://{config_bucket}/{config_key}")
        response = s3_client.get_object(Bucket=config_bucket, Key=config_key)
        config_content = response['Body'].read().decode('utf-8')
        
        routing_rules = json.loads(config_content)
        
        # Sort by priority for faster matching
        routing_rules.sort(key=lambda x: x.get('priority', 999))
        
        # Cache the config
        cached_config = routing_rules
        config_last_modified = last_modified
        
        print(f"Loaded {len(routing_rules)} routing rules")
        return routing_rules
        
    except Exception as e:
        print(f"Error loading config from S3: {e}")
        print("NO FALLBACK RULES - FILES WILL NOT BE PROCESSED")
        return []  # Return empty list = no processing

def get_fallback_config():
    """Fallback configuration if S3 config fails"""
    return [
        {
            'name': 'Fallback Punchh',
            'priority': 1,
            'source_patterns': ['Punchh/', 'punchh/'],
            'pattern_type': 'multi_prefix',
            'destination_bucket': 'vh-punchh-prod',
            'destination_prefix': 'CheckIns/raw/',
            'file_types': ['.csv', '.json']
        }
    ]

def find_best_destination(source_key, routing_rules):
    """Find the best matching rule based on priority"""
    filename = source_key.split('/')[-1]
    
    # Skip hidden files and directories
    if filename.startswith('.') or source_key.endswith('/'):
        return None
    
    # Rules are already sorted by priority, so return first match
    for rule in routing_rules:
        if matches_rule(source_key, filename, rule):
            print(f"Matched rule: '{rule['name']}' (priority: {rule.get('priority', 'N/A')})")
            return rule
    
    return None

def matches_rule(source_key, filename, rule):
    """Check if source matches the rule patterns"""
    
    # Skip if rule is disabled
    if not rule.get('enabled', True):
        return False
    
    # Check file type first (quick elimination)
    if not check_file_type(filename, rule.get('file_types', [])):
        return False
    
    pattern_type = rule.get('pattern_type', 'prefix')
    source_pattern = rule.get('source_pattern', '')
    
    # Valid pattern types - only these are allowed
    valid_pattern_types = ['prefix_with_filename_filter', 'prefix']
    
    # Check path pattern first - EXACT matching with single pattern only
    path_matches = False
    
    # Get single source pattern (no arrays)
    source_pattern = rule.get('source_pattern', '')
    
    # Extract just the folder path from the source key for exact comparison
    source_folder = '/'.join(source_key.split('/')[:-1]) + '/' if '/' in source_key else ''
    
    # Check if pattern_type is valid AND source_folder matches exactly
    if pattern_type in valid_pattern_types and source_folder == source_pattern:
        path_matches = True
        print(f"Valid pattern type '{pattern_type}' and exact folder match: '{source_folder}' == '{source_pattern}'")
    else:
        if pattern_type not in valid_pattern_types:
            print(f"Invalid pattern_type: '{pattern_type}'. Must be one of: {valid_pattern_types}")
        if source_folder != source_pattern:
            print(f"Folder mismatch: '{source_folder}' != '{source_pattern}'")
        return False
    
    # If path doesn't match, return False
    if not path_matches:
        return False
    
    # For patterns with filename filtering, check filename
    if pattern_type == 'prefix_with_filename_filter':
        return check_filename_filter(filename, rule.get('filename_filter', {}))
    
    return True

def apply_smart_routing(source_key, rule):
    """Apply smart routing to determine specific destination based on keywords"""
    smart_config = rule['smart_routing']
    keyword_mapping = smart_config['keyword_mapping']
    default_destination = smart_config['default_destination']
    
    # Check for keywords in the source path (case insensitive)
    source_lower = source_key.lower()
    
    for keyword, destination_prefix in keyword_mapping.items():
        if keyword.lower() in source_lower:
            # Create enhanced rule with specific destination
            enhanced_rule = rule.copy()
            enhanced_rule['destination_prefix'] = destination_prefix
            enhanced_rule['matched_keyword'] = keyword
            print(f"🔍 Smart routing: Found keyword '{keyword}' → {destination_prefix}")
            return enhanced_rule
    
    # No keyword match, use default
    enhanced_rule = rule.copy()
    enhanced_rule['destination_prefix'] = default_destination
    enhanced_rule['matched_keyword'] = 'default'
    print(f"🔍 Smart routing: No keyword match → {default_destination}")
    return enhanced_rule

def check_filename_filter(filename, filename_filter):
    """Check if filename matches the specified filter criteria"""
    if not filename_filter:
        return True
    
    filter_type = filename_filter.get('type', 'none')
    case_sensitive = filename_filter.get('case_sensitive', False)
    
    # Prepare filename for comparison
    check_filename = filename if case_sensitive else filename.lower()
    
    if filter_type == 'starts_with':
        value = filename_filter['value']
        check_value = value if case_sensitive else value.lower()
        result = check_filename.startswith(check_value)
        print(f"Filename filter: '{filename}' starts with '{value}' = {result}")
        return result
    
    elif filter_type == 'not_starts_with':
        value = filename_filter['value']
        check_value = value if case_sensitive else value.lower()
        result = not check_filename.startswith(check_value)
        print(f"Filename filter: '{filename}' NOT starts with '{value}' = {result}")
        return result
    
    elif filter_type == 'ends_with':
        value = filename_filter['value']
        check_value = value if case_sensitive else value.lower()
        result = check_filename.endswith(check_value)
        print(f"Filename filter: '{filename}' ends with '{value}' = {result}")
        return result
    
    elif filter_type == 'contains':
        value = filename_filter['value']
        check_value = value if case_sensitive else value.lower()
        result = check_value in check_filename
        print(f"Filename filter: '{filename}' contains '{value}' = {result}")
        return result
    
    elif filter_type == 'regex':
        pattern = filename_filter['value']
        flags = 0 if case_sensitive else re.IGNORECASE
        result = bool(re.search(pattern, filename, flags))
        print(f"Filename filter: '{filename}' matches regex '{pattern}' = {result}")
        return result
    
    elif filter_type == 'multiple_patterns':
        patterns = filename_filter.get('patterns', [])
        match_logic = filename_filter.get('match_logic', 'any')  # 'any' or 'all'
        
        results = []
        for pattern in patterns:
            pattern_result = check_filename_filter(filename, pattern)
            results.append(pattern_result)
        
        if match_logic == 'any':
            final_result = any(results)
        else:  # 'all'
            final_result = all(results)
        
        print(f"Multiple patterns: {results} -> {match_logic} = {final_result}")
        return final_result
    
    # Default: no filter means match
    return True

def check_file_type(filename, allowed_types):
    """Check if file type is allowed"""
    if not allowed_types:
        return True
        
    file_ext = '.' + filename.split('.')[-1] if '.' in filename else ''
    return file_ext.lower() in [ext.lower() for ext in allowed_types]

def process_file(s3_client, source_bucket, source_key, destination_info):
    """Process and move file to destination"""
    try:
        filename = source_key.split('/')[-1]
        
        # Generate destination filename
        if destination_info.get('add_timestamp', True):
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            name, ext = filename.rsplit('.', 1) if '.' in filename else (filename, '')
            destination_filename = f"{name}_{timestamp}" + (f".{ext}" if ext else "")
        else:
            destination_filename = filename
        
        destination_key = f"{destination_info['destination_prefix']}{destination_filename}"
        
        # Copy file with metadata
        copy_source = {'Bucket': source_bucket, 'Key': source_key}
        
        metadata = {
            'source-bucket': source_bucket,
            'source-key': source_key,
            'processed-by': 'configurable-file-mover',
            'processed-at': datetime.now().isoformat(),
            'routing-rule': destination_info['name'],
            'rule-priority': str(destination_info.get('priority', 'N/A'))
        }
        
        # Add smart routing info if available
        if 'matched_keyword' in destination_info:
            metadata['matched-keyword'] = destination_info['matched_keyword']
        
        s3_client.copy_object(
            CopySource=copy_source,
            Bucket=destination_info['destination_bucket'],
            Key=destination_key,
            MetadataDirective='REPLACE',
            Metadata=metadata
        )
        
        print(f"SUCCESS: {source_key}")
        print(f"   -> s3://{destination_info['destination_bucket']}/{destination_key}")
        print(f"   -> Rule: {destination_info['name']} (Priority: {destination_info.get('priority', 'N/A')})")
        
        # Delete source if configured
        if destination_info.get('delete_source', False):
            s3_client.delete_object(Bucket=source_bucket, Key=source_key)
            print(f"Deleted source file")
        
        return {
            'success': True,
            'source': f"s3://{source_bucket}/{source_key}",
            'destination': f"s3://{destination_info['destination_bucket']}/{destination_key}",
            'rule_used': destination_info['name'],
            'priority': destination_info.get('priority', 'N/A')
        }
        
    except Exception as e:
        error_msg = f"Failed to process {source_key}: {str(e)}"
        print(f"ERROR: {error_msg}")
        return {
            'success': False,
            'source': f"s3://{source_bucket}/{source_key}",
            'error': error_msg
        }