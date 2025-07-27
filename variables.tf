# variables.tf
variable "aws_region" {
  description = "AWS region"
  type        = string
}

variable "source_bucket" {
  description = "Source S3 bucket name"
  type        = string
}

# Define all destination buckets that the Lambda needs access to
variable "destination_buckets" {
  description = "List of destination S3 bucket names"
  type        = list(string)
  default = [
    "vh-punchh-prod",
    "vh-alohasales-prod", 
    "vh-inventory-prod"
  ]
}


variable "config_bucket" {
  description = "S3 bucket where config file is located"
  type        = string
}

variable "config_file_key" {
  description = "file name and location of config file within the config_bucket"
  type        = string
}