# DynamoDB Table Terraform Setup for IFCER

This document provides complete Terraform code to create the DynamoDB table required for the IFCER certification service.

## Table Overview

**Table Name:** `ifcer-certifications`

**Primary Key:**
- Partition Key: `file_key` (String) - S3 key of the original file
- Sort Key: `processing_timestamp` (String) - ISO8601 timestamp

**Global Secondary Indexes:**
1. **filename-index** - Search by filename
2. **date-index** - Query by date range

**Features:**
- Pay-per-request billing (cost-effective for batch workloads)
- TTL enabled for automatic record deletion
- Point-in-time recovery enabled
- Server-side encryption enabled

---

## Complete Terraform Configuration

### main.tf

```hcl
terraform {
  required_version = ">= 1.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = "eu-south-1"  # Change to your region

  default_tags {
    tags = {
      Project     = "IFCER"
      ManagedBy   = "Terraform"
      Environment = "production"
    }
  }
}

resource "aws_dynamodb_table" "ifcer_certifications" {
  name         = "ifcer-certifications"
  billing_mode = "PAY_PER_REQUEST"

  # Primary Key
  hash_key  = "file_key"
  range_key = "processing_timestamp"

  # Attribute Definitions (only for keys and index keys)
  attribute {
    name = "file_key"
    type = "S"
  }

  attribute {
    name = "processing_timestamp"
    type = "S"
  }

  attribute {
    name = "filename"
    type = "S"
  }

  attribute {
    name = "date_partition"
    type = "S"
  }

  # Global Secondary Index 1: filename-index
  # Used for searching files by filename
  global_secondary_index {
    name            = "filename-index"
    hash_key        = "filename"
    range_key       = "processing_timestamp"
    projection_type = "ALL"
  }

  # Global Secondary Index 2: date-index
  # Used for querying by date range
  global_secondary_index {
    name            = "date-index"
    hash_key        = "date_partition"
    range_key       = "processing_timestamp"
    projection_type = "ALL"
  }

  # Time to Live (TTL) Configuration
  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  # Point-in-Time Recovery
  point_in_time_recovery {
    enabled = true
  }

  # Server-Side Encryption
  server_side_encryption {
    enabled = true
  }

  tags = {
    Name = "IFCER Certifications"
  }
}

# Output the table details
output "table_name" {
  value = aws_dynamodb_table.ifcer_certifications.name
}

output "table_arn" {
  value = aws_dynamodb_table.ifcer_certifications.arn
}

output "iam_policy" {
  description = "IAM policy for ECS task role"
  value = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "dynamodb:PutItem",
          "dynamodb:GetItem",
          "dynamodb:Query",
          "dynamodb:BatchGetItem",
          "dynamodb:DescribeTable"
        ]
        Resource = [
          aws_dynamodb_table.ifcer_certifications.arn,
          "${aws_dynamodb_table.ifcer_certifications.arn}/index/*"
        ]
      }
    ]
  })
}
```

---

## Usage Instructions

### 1. Create a new directory and save the code

```bash
mkdir terraform-dynamodb
cd terraform-dynamodb
# Save the above code to main.tf
```

### 2. Initialize Terraform

```bash
terraform init
```

### 3. Review the plan

```bash
terraform plan
```

### 4. Create the table

```bash
terraform apply
```

Type `yes` when prompted.

### 5. Get the outputs

```bash
terraform output
terraform output -raw iam_policy  # Get IAM policy JSON
```

---

## Table Schema Details

### Primary Key Structure

```
file_key (HASH) + processing_timestamp (RANGE)
```

**Example:**
```
file_key: "documents/2025/invoice_001.pdf"
processing_timestamp: "2025-01-15T10:30:00.000Z"
```

### Global Secondary Index 1: filename-index

```
filename (HASH) + processing_timestamp (RANGE)
```

**Purpose:** Find all certifications for a specific filename

**Query Example:**
```python
table.query(
    IndexName='filename-index',
    KeyConditionExpression='filename = :fn',
    ExpressionAttributeValues={':fn': 'invoice_001.pdf'}
)
```

### Global Secondary Index 2: date-index

```
date_partition (HASH) + processing_timestamp (RANGE)
```

**Purpose:** Query certifications by month

**Query Example:**
```python
table.query(
    IndexName='date-index',
    KeyConditionExpression='date_partition = :dp AND processing_timestamp BETWEEN :start AND :end',
    ExpressionAttributeValues={
        ':dp': '2025-01',
        ':start': '2025-01-01T00:00:00.000Z',
        ':end': '2025-01-31T23:59:59.999Z'
    }
)
```

---

## Attributes Stored

| Attribute | Type | Description |
|-----------|------|-------------|
| `file_key` | String | S3 key of original file (PK) |
| `processing_timestamp` | String | ISO8601 timestamp (SK) |
| `filename` | String | Base filename |
| `date_partition` | String | YYYY-MM format |
| `file_hash` | String | SHA-256 hash |
| `hash_algorithm` | String | "sha256" |
| `digital_signature` | String | Vendor signature |
| `vendor_timestamp` | String | Vendor timestamp |
| `signed_file_key` | String | S3 key of P7M file |
| `file_size` | Number | Original size in bytes |
| `signed_file_size` | Number | Signed size in bytes |
| `status` | String | "completed" or "failed" |
| `error_message` | String | Error if failed |
| `ttl` | Number | Unix timestamp for deletion |

---

## Customization Options

### Change Table Name

Replace `"ifcer-certifications"` with your desired name:

```hcl
name = "your-custom-table-name"
```

### Change Region

```hcl
provider "aws" {
  region = "us-east-1"  # Your region
}
```

### Use Provisioned Capacity

For predictable high-volume workloads:

```hcl
billing_mode   = "PROVISIONED"
read_capacity  = 5
write_capacity = 5

# Add to each GSI:
global_secondary_index {
  # ... other settings
  read_capacity  = 5
  write_capacity = 5
}
```

### Disable TTL

```hcl
ttl {
  enabled = false
}
```

### Disable Point-in-Time Recovery

```hcl
point_in_time_recovery {
  enabled = false
}
```

---

## IAM Policy for ECS Task Role

After creating the table, use this IAM policy for your ECS task role:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "dynamodb:PutItem",
        "dynamodb:GetItem",
        "dynamodb:Query",
        "dynamodb:BatchGetItem",
        "dynamodb:DescribeTable"
      ],
      "Resource": [
        "arn:aws:dynamodb:eu-south-1:ACCOUNT_ID:table/ifcer-certifications",
        "arn:aws:dynamodb:eu-south-1:ACCOUNT_ID:table/ifcer-certifications/index/*"
      ]
    }
  ]
}
```

Replace `ACCOUNT_ID` with your AWS account ID.

---

## Verify Table Creation

```bash
# Check table status
aws dynamodb describe-table --table-name ifcer-certifications

# List tables
aws dynamodb list-tables

# Check GSI status
aws dynamodb describe-table --table-name ifcer-certifications \
  --query 'Table.GlobalSecondaryIndexes[*].[IndexName,IndexStatus]' \
  --output table
```

---

## Cost Estimate

**Pay-Per-Request Mode:**
- 10,000 writes/month: ~$0.01
- 50,000 reads/month: ~$0.02
- Storage (10 MB): ~$0.00
- **Total: ~$0.03/month**

**Note:** Pay-per-request is ideal for batch workloads with variable traffic.

---

## Cleanup

To delete the table:

```bash
terraform destroy
```

**Warning:** This permanently deletes all data!

---

## Troubleshooting

### Table already exists

```bash
# Import existing table
terraform import aws_dynamodb_table.ifcer_certifications ifcer-certifications
```

### Permission denied

Ensure your AWS credentials have `dynamodb:CreateTable` permission.

### GSI creation in progress

GSIs are created asynchronously. Wait 1-2 minutes and check status:

```bash
aws dynamodb describe-table --table-name ifcer-certifications \
  --query 'Table.GlobalSecondaryIndexes[*].IndexStatus'
```

Status should show `ACTIVE` when ready.
