resource "aws_dynamodb_table" "ifcer_certifications" {
  name           = "ifcer-certifications"
  billing_mode   = "PAY_PER_REQUEST"
  hash_key       = "Id"

  # Primary Key
  attribute {
    name = "Id"
    type = "S"
  }

  # GSI Attributes
  attribute {
    name = "filename"
    type = "S"
  }

  attribute {
    name = "date_partition"
    type = "S"
  }

  attribute {
    name = "processing_timestamp"
    type = "S"
  }

  # Global Secondary Index 1: filename-index
  global_secondary_index {
    name            = "filename-index"
    hash_key        = "filename"
    range_key       = "processing_timestamp"
    projection_type = "ALL"
  }

  # Global Secondary Index 2: date-index
  global_secondary_index {
    name            = "date-index"
    hash_key        = "date_partition"
    range_key       = "processing_timestamp"
    projection_type = "ALL"
  }

  # TTL Configuration
  ttl {
    enabled        = true
    attribute_name = "ttl"
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
    Name      = "ifcer-certifications"
    Service   = "IFCER Batch Service"
    ManagedBy = "Terraform"
  }
}
