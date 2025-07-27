
# main.tf
terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

# IAM role for Lambda function
resource "aws_iam_role" "multi_path_lambda_role" {
  name = "multi-path-file-mover-lambda-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_policy" "multi_path_lambda_policy" {
  name        = "multi-path-file-mover-lambda-policy"
  description = "IAM policy for Lambda to move files between multiple S3 buckets"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream", 
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:*:*:*"
      },
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:GetObjectVersion",
          "s3:DeleteObject",
          "s3:HeadObject"
        ]
        Resource = [
          "arn:aws:s3:::${var.source_bucket}/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:PutObjectAcl"
        ]
        Resource = [
          for bucket in var.destination_buckets : "arn:aws:s3:::${bucket}/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "s3:ListBucket"
        ]
        Resource = concat(
          ["arn:aws:s3:::${var.source_bucket}"],
          [for bucket in var.destination_buckets : "arn:aws:s3:::${bucket}"]
        )
      }
    ]
  })
}

# Attach policy to role
resource "aws_iam_role_policy_attachment" "multi_path_lambda_policy_attachment" {
  role       = aws_iam_role.multi_path_lambda_role.name
  policy_arn = aws_iam_policy.multi_path_lambda_policy.arn
}

# Create the Lambda function code
data "archive_file" "multi_path_lambda_zip" {
  type        = "zip"
  output_path = "multi_path_file_mover.zip"
  
  source {
    content  = file("${path.module}/lambda_function.py")
    filename = "lambda_function.py"
  }
}

# Lambda function
resource "aws_lambda_function" "multi_path_file_mover" {
  filename         = data.archive_file.multi_path_lambda_zip.output_path
  function_name    = "sftp-file-mover"
  role            = aws_iam_role.multi_path_lambda_role.arn
  handler         = "lambda_function.lambda_handler"
  source_code_hash = data.archive_file.multi_path_lambda_zip.output_base64sha256
  runtime         = "python3.9"
  timeout         = 180  # 6 minutes for processing multiple files
  memory_size     = 512  # More memory for better performance

  environment {
    variables = {
      SOURCE_BUCKET = var.source_bucket
      LOG_LEVEL    = "INFO"
      CONFIG_BUCKET = var.config_bucket
      CONFIG_FILE_KEY = var.config_file_key
    }
  }

  tags = {
    Name = "MultiPathFileMover"
  }
}

# S3 bucket notification to trigger Lambda for all objects
resource "aws_s3_bucket_notification" "multi_path_notification" {
  bucket = var.source_bucket

  lambda_function {
    lambda_function_arn = aws_lambda_function.multi_path_file_mover.arn
    events              = ["s3:ObjectCreated:*"]
    # No filter_prefix - this Lambda handles all files and routes them
  }

  depends_on = [aws_lambda_permission.allow_s3_invoke_multi_path]
}

# Permission for S3 to invoke Lambda
resource "aws_lambda_permission" "allow_s3_invoke_multi_path" {
  statement_id  = "AllowExecutionFromS3Bucket"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.multi_path_file_mover.function_name
  principal     = "s3.amazonaws.com"
  source_arn    = "arn:aws:s3:::${var.source_bucket}"
}

# CloudWatch Log Group for Lambda
resource "aws_cloudwatch_log_group" "multi_path_lambda_logs" {
  name              = "/aws/lambda/${aws_lambda_function.multi_path_file_mover.function_name}"
  retention_in_days = 30
}

# outputs.tf
output "lambda_function_name" {
  description = "Name of the multi-path Lambda function"
  value       = aws_lambda_function.multi_path_file_mover.function_name
}

output "lambda_function_arn" {
  description = "ARN of the multi-path Lambda function"
  value       = aws_lambda_function.multi_path_file_mover.arn
}
