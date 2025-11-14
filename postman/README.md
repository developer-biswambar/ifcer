# IFCER Batch Service - Postman Collection

This folder contains Postman collection and environment files for testing the IFCER Batch Service APIs.

## Files

- **IFCER_Batch_Service.postman_collection.json** - Complete API collection with all endpoints
- **IFCER_Local.postman_environment.json** - Local development environment (localhost:8000)
- **IFCER_Staging.postman_environment.json** - Staging environment
- **IFCER_Production.postman_environment.json** - Production environment

## Quick Start

### 1. Import Collection

1. Open Postman
2. Click **Import** button (top left)
3. Drag and drop `IFCER_Batch_Service.postman_collection.json`
4. Click **Import**

### 2. Import Environments

1. Click **Import** button
2. Drag and drop all three environment JSON files:
   - `IFCER_Local.postman_environment.json`
   - `IFCER_Staging.postman_environment.json`
   - `IFCER_Production.postman_environment.json`
3. Click **Import**

### 3. Select Environment

1. Click the environment dropdown (top right)
2. Select your desired environment:
   - **IFCER - Local** for local development
   - **IFCER - Staging** for staging
   - **IFCER - Production** for production

### 4. Configure Environment Variables

1. Click the environment dropdown → **Edit** (eye icon)
2. Update the `base_url` if needed
3. Update other variables as needed:
   - `start_date` - Start date for date range queries
   - `end_date` - End date for date range queries
   - `prefix` - S3 prefix for batch processing
   - `date_partition` - Month partition (YYYY-MM format)
   - `filename` - Sample filename for testing
   - `sample_file_key` - Sample S3 file key
   - `sample_signed_key` - Sample signed file key

## Environment Variables

### Required Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `base_url` | API base URL | `http://localhost:8000` |

### Optional Variables (with defaults)

| Variable | Description | Default |
|----------|-------------|---------|
| `start_date` | Batch processing start date | `2025-01-01T00:00:00Z` |
| `end_date` | Batch processing end date | `2025-01-31T23:59:59Z` |
| `prefix` | S3 prefix for filtering | `""` (empty) |
| `date_partition` | Month partition (YYYY-MM) | `2025-01` |
| `filename` | Sample filename | `invoice.pdf` |
| `sample_file_key` | Sample file S3 key | `uploads/invoice.pdf` |
| `sample_signed_key` | Sample signed file S3 key | `signed/invoice.pdf.p7m` |

## API Endpoints

### Root
- **GET /** - Service information and status

### Processing
- **GET /health** - Health check
- **POST /process** - Batch process files by date range
- **POST /recertify** - Recertify a single file
- **GET /failed-files** - Get failed file processing records
- **POST /reprocess-failed** - Reprocess failed files

### Files
- **POST /file-details** - Get file details and signing status
- **POST /files-list** - List files by date range
- **GET /download/original** - Download original file
- **GET /download/signed** - Download signed P7M file
- **DELETE /original** - Delete original file
- **DELETE /signed** - Delete signed file

### Certificates
- **GET /certificates** - Get all certificates from InfoCert
- **GET /certificates/active** - Get only active certificates

## Usage Examples

### 1. Batch Process Files

```json
POST {{base_url}}/process
{
  "start_date": "2025-01-01T00:00:00Z",
  "end_date": "2025-01-31T23:59:59Z",
  "prefix": "abc"
}
```

This will process all files in `uploads/abc/` uploaded between Jan 1-31, 2025.

### 2. Recertify Single File

```json
POST {{base_url}}/recertify
{
  "file_key": "uploads/invoice.pdf"
}
```

### 3. Get Failed Files

```
GET {{base_url}}/failed-files?date_partition=2025-01
```

### 4. Reprocess Failed Files

```json
POST {{base_url}}/reprocess-failed
{
  "file_keys": [
    "uploads/invoice-123.pdf",
    "uploads/invoice-456.pdf"
  ]
}
```

Or reprocess by date partition:

```json
POST {{base_url}}/reprocess-failed
{
  "date_partition": "2025-01"
}
```

### 5. Download Signed File

```
GET {{base_url}}/download/signed?original_file_key=uploads/invoice.pdf
```

Or using direct P7M key:

```
GET {{base_url}}/download/signed?signed_file_key=signed/invoice.pdf.p7m
```

### 6. Delete Files

Delete original:
```
DELETE {{base_url}}/original?file_key=uploads/invoice.pdf
```

Delete signed:
```
DELETE {{base_url}}/signed?file_key=signed/invoice.pdf.p7m
```

## Customizing for Your Environment

### Update Base URL

1. Select your environment (e.g., **IFCER - Production**)
2. Click the eye icon → **Edit**
3. Change `base_url` to your actual API URL:
   - Local: `http://localhost:8000`
   - Staging: `https://staging-api.ifcer.example.com`
   - Production: `https://api.ifcer.example.com`

### Update Test Data

Modify the following variables to match your test data:
- `sample_file_key` - Use an actual file key from your S3 bucket
- `sample_signed_key` - Use an actual signed file key
- `filename` - Use a filename that exists in your bucket

## Tips

1. **Use Variables**: All requests use environment variables (e.g., `{{base_url}}`) for easy switching between environments
2. **Update Dates**: Adjust `start_date` and `end_date` to match your data
3. **Test Prefix**: Use the `prefix` variable to test different S3 folder structures
4. **Check Responses**: Each endpoint has detailed descriptions to help understand the responses

## Troubleshooting

### Connection Refused
- Make sure the service is running (`uvicorn app.main:app --reload`)
- Verify the `base_url` is correct

### 404 Not Found
- Check that you're using the correct environment
- Verify the endpoint path is correct

### 500 Internal Server Error
- Check the service logs for detailed error messages
- Verify your AWS credentials and permissions
- Ensure S3 bucket and DynamoDB table exist

## Support

For issues or questions, refer to the main project documentation or check the API logs.
