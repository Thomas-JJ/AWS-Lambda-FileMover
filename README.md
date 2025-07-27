# AWS Lambda File Mover

An intelligent, configurable AWS Lambda function that automatically routes files from a source S3 bucket to specific destinations based on path patterns and filename filters.

## Overview

This solution provides enterprise-grade file routing for data pipelines, automatically moving files from SFTP landing zones to appropriate processing folders based on configurable rules stored in S3.

## Architecture

```
Source S3 Bucket → Lambda Function → Destination Buckets
     ↓                    ↓               ↓
SFTP Files         Config-Driven      Raw Data Folders
                   File Routing
```

## Features

- **🎯 Intelligent Routing**: Route files based on folder paths and filename patterns
- **⚙️ S3-Based Configuration**: Update routing rules without redeploying code
- **🔒 Secure**: Minimal IAM permissions with least-privilege access
- **📊 Observable**: Full CloudWatch logging and monitoring
- **🚀 Serverless**: Pay only for execution time, auto-scaling
- **🛡️ Reliable**: Built-in error handling with no fallback processing

## Quick Start

### Prerequisites

- AWS CLI configured
- Terraform >= 1.0
- S3 buckets already created
- Appropriate AWS permissions

### 1. Clone and Configure

```bash
git clone <repository>
cd aws-lambda-filemover
cp terraform.tfvars.example terraform.tfvars
```

### 2. Update Configuration

Edit `terraform.tfvars`:

```hcl
source_bucket = "fg-sftp-server"
destination_buckets = [
  "vh-punchh-prod",
  "vh-alohasales-prod", 
  "vh-inventory-prod"
]
aws_region = "us-east-2"
config_bucket = "fg-sftp-server"
config_file_key = "config/routing-rules.json"
```

### 3. Create Routing Rules

Upload your routing configuration to S3:

```bash
aws s3 cp routing-rules.json s3://fg-sftp-server/config/routing-rules.json
```

### 4. Deploy

```bash
terraform init
terraform plan
terraform apply
```

## Configuration

### Routing Rules Format

Store routing rules as JSON in S3. Each rule defines how to route files:

```json
[
  {
    "name": "Punchh CheckIns - checkin- files only",
    "priority": 1,
    "source_pattern": "Punchh/",
    "pattern_type": "prefix_with_filename_filter",
    "filename_filter": {
      "type": "starts_with",
      "value": "checkin-",
      "case_sensitive": false
    },
    "destination_bucket": "vh-punchh-prod",
    "destination_prefix": "CheckIns/raw/",
    "file_types": [".csv"],
    "add_timestamp": true,
    "delete_source": true,
    "description": "Process Punchh check-in files to raw folder",
    "enabled": true
  }
]
```

### Rule Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `name` | ✅ | Human-readable rule name |
| `priority` | ✅ | Processing priority (lower = higher priority) |
| `source_pattern` | ✅ | Exact folder path to match (e.g., "Punchh/") |
| `pattern_type` | ✅ | Must be "prefix_with_filename_filter" or "prefix" |
| `destination_bucket` | ✅ | Target S3 bucket name |
| `destination_prefix` | ✅ | Target folder path (e.g., "CheckIns/raw/") |
| `file_types` | ✅ | Allowed file extensions (e.g., [".csv", ".json"]) |
| `filename_filter` | ❌ | Filename matching rules (required for prefix_with_filename_filter) |
| `add_timestamp` | ❌ | Append timestamp to end of filename (default: true) |
| `delete_source` | ❌ | Delete source file after copy (default: false) |
| `enabled` | ❌ | Enable/disable rule (default: true) |

### Filename Filter Options

```json
{
  "type": "starts_with",     // starts_with, ends_with, contains, regex
  "value": "checkin-",       // Pattern to match
  "case_sensitive": false    // Case sensitivity (default: false)
}
```

### Pattern Types

- **`prefix`**: Simple folder path matching
- **`prefix_with_filename_filter`**: Folder path + filename pattern matching

## Examples

### Example 1: Route Check-in Files
```json
{
  "name": "App CheckIns",
  "priority": 1,
  "source_pattern": "App/",
  "pattern_type": "prefix_with_filename_filter",
  "filename_filter": {
    "type": "starts_with",
    "value": "checkin-"
  },
  "destination_bucket": "bucket-app-prod",
  "destination_prefix": "CheckIns/raw/",
  "file_types": [".csv"]
}
```

### Example 2: Route All Sales Files
```json
{
  "name": "Sales Data",
  "priority": 10,
  "source_pattern": "sales/",
  "pattern_type": "prefix",
  "destination_bucket": "bucket-sales-prod",
  "destination_prefix": "SalesSummary/raw/",
  "file_types": [".csv", ".xlsx"]
}
```

## File Processing Logic

1. **S3 Event Trigger**: File uploaded to source bucket
2. **Load Configuration**: Read routing rules from S3 config file
3. **Rule Matching**: Find highest priority rule that matches file path and name
4. **File Processing**: Copy file to destination with optional transformations
5. **Cleanup**: Optionally delete source file
6. **Logging**: Record all actions in CloudWatch

### Processing Flow

```
File: "app/checkin-daily-20250126.csv"
│
├─ Load routing rules from S3 config
├─ Check folder: "app/" matches rule source_pattern ✅
├─ Check filename: "checkin-daily-20250126.csv" starts with "checkin-" ✅
├─ Copy to: "app/CheckIns/raw/checkin-daily-20250126_20250126_120000.csv"
└─ Delete source (if configured) ✅
```

## Monitoring

### CloudWatch Logs

View Lambda execution logs:
```bash
aws logs tail /aws/lambda/multi-path-file-mover --follow
```

### Key Metrics

Monitor these CloudWatch metrics:
- Lambda invocations
- Lambda errors  
- Lambda duration
- S3 file counts by folder

### Troubleshooting

**Common Issues:**

1. **Config file not loading**: Check JSON syntax and S3 permissions
2. **Files not matching**: Verify source_pattern and filename_filter
3. **Permission errors**: Check IAM roles for S3 access
4. **No files processed**: Verify rules are enabled and have correct priority

**Debug Commands:**
```bash
# Test Lambda manually
aws lambda invoke --function-name multi-path-file-mover --payload file://test-event.json response.json

# Check recent logs
aws logs filter-log-events --log-group-name "/aws/lambda/multi-path-file-mover" --start-time $(date -d '5 minutes ago' +%s)000
```

## Security

- **Least Privilege**: Lambda only has minimum required S3 permissions
- **No Fallback Processing**: Files are ignored if no rules match (no defaults)
- **Secure Configuration**: Rules stored in S3 with proper access controls
- **Audit Trail**: All file movements logged to CloudWatch

## Cost Optimization

- **Serverless**: Pay only for execution time
- **Efficient Processing**: Bulk file handling in single invocation
- **Smart Caching**: Configuration cached between executions
- **Minimal Memory**: Optimized for 256-512MB memory usage

## Terraform Resources

This project creates:
- AWS Lambda function with Python 3.9 runtime
- IAM role and policies for S3 access
- S3 event notifications for automatic triggering
- CloudWatch log group with retention policy
- Optional CloudWatch dashboard for monitoring

## Support

For issues or questions:
1. Check CloudWatch logs for error details
2. Verify configuration file syntax
3. Test rules with manual Lambda invocation
4. Review IAM permissions for S3 access

## License

This project is licensed under the MIT License - see the LICENSE file for details.
