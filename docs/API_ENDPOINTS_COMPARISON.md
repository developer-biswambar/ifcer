# API Endpoints Comparison

## Processing Endpoints Overview

The IFCER Batch Service now has three main processing endpoints, all using the optimized **batch InfoCert API**:

---

## 1. `/process` - Date Range Processing

**Purpose**: Process files from S3 within a specified date range

**Input**:
```json
{
  "start_date": "2025-01-01T00:00:00Z",
  "end_date": "2025-01-31T23:59:59Z",
  "prefix": "optional-prefix",
  "reprocess": false
}
```

**Use Cases**:
- ✅ Monthly batch processing of new uploads
- ✅ Process files uploaded in a specific time period
- ✅ Smart processing (skips already-processed files by default)
- ✅ Organized by date ranges

**Behavior**:
- Lists files from S3 by upload date
- Checks DynamoDB to skip already-processed files (unless `reprocess=True`)
- Processes in batches using InfoCert batch signing API
- Continue-on-error (processes all files, tracks failures)

**Example**:
```bash
curl -X POST "http://localhost:8000/process" \
  -H "Content-Type: application/json" \
  -d '{
    "start_date": "2025-01-01T00:00:00Z",
    "end_date": "2025-01-31T23:59:59Z",
    "prefix": "invoices"
  }'
```

---

## 2. `/reprocess-failed` - Retry Failed Files

**Purpose**: Reprocess files that previously failed processing

**Input**:
```json
{
  "file_keys": ["uploads/file1.pdf", "uploads/file2.pdf"],
  "date_partition": "2025-01"
}
```

**Use Cases**:
- ✅ Retry files that failed due to network issues
- ✅ Reprocess files that had temporary API errors
- ✅ Bulk retry of all failures from a specific month
- ✅ Targeted retry of specific failed files

**Behavior**:
- Queries DynamoDB for files with `status="failed"`
- Or accepts specific file_keys to reprocess
- Processes in batches using InfoCert batch signing API
- Updates DynamoDB records on success

**Example 1** (Specific files):
```bash
curl -X POST "http://localhost:8000/reprocess-failed" \
  -H "Content-Type: application/json" \
  -d '{
    "file_keys": [
      "uploads/invoice-123.pdf",
      "uploads/invoice-456.pdf"
    ]
  }'
```

**Example 2** (All failures from January 2025):
```bash
curl -X POST "http://localhost:8000/reprocess-failed" \
  -H "Content-Type: application/json" \
  -d '{
    "date_partition": "2025-01"
  }'
```

---

## 3. `/resign` - Re-sign Specific Files (NEW!)

**Purpose**: Re-sign any files with fresh signatures and timestamps

**Input**:
```json
{
  "file_keys": ["uploads/file1.pdf", "uploads/file2.pdf"]
}
```

**Use Cases**:
- ✅ Re-sign files that need updated timestamps
- ✅ Bulk re-signing after certificate renewal
- ✅ Create new signatures for already-signed files
- ✅ Re-certify files for compliance updates

**Behavior**:
- Accepts specific file_keys from S3 (any files)
- Fetches metadata from S3
- Processes in batches using InfoCert batch signing API
- Creates NEW signatures and timestamps (even if already signed)
- Updates/overwrites DynamoDB records

**Key Difference**:
⚠️ **Always creates NEW signatures**, even if files were already successfully processed. Use this when you explicitly want fresh signatures.

**Example**:
```bash
curl -X POST "http://localhost:8000/resign" \
  -H "Content-Type: application/json" \
  -d '{
    "file_keys": [
      "uploads/invoice-123.pdf",
      "uploads/invoice-456.pdf",
      "uploads/2025-01/contract.pdf"
    ]
  }'
```

---

## Comparison Table

| Feature | `/process` | `/reprocess-failed` | `/resign` |
|---------|------------|---------------------|-----------|
| **Input** | Date range + prefix | Failed files or date partition | Specific file keys |
| **Source** | S3 date range query | DynamoDB failed records | User-provided file list |
| **Skip Already-Processed** | Yes (by default) | N/A (only processes failed) | No (always re-signs) |
| **Use Case** | New files in date range | Retry failures | Fresh signatures |
| **Batch API** | ✅ Yes | ✅ Yes | ✅ Yes |
| **Continue-on-Error** | ✅ Yes | ✅ Yes | ✅ Yes |
| **DynamoDB Update** | Creates new records | Updates existing records | Overwrites records |

---

## Performance (All Endpoints)

All three endpoints use the **optimized batch InfoCert API**:

- **Old approach** (per-file): 100 files = 100 API calls
- **New approach** (batch): 100 files = 2 API calls (with batch size 50)
- **Performance gain**: **98% reduction in API calls**

### API Call Reduction Examples

| Files | Batch Size | API Calls (Old) | API Calls (New) | Reduction |
|-------|------------|-----------------|-----------------|-----------|
| 10    | 50         | 10              | 1               | 90%       |
| 50    | 50         | 50              | 1               | 98%       |
| 100   | 50         | 100             | 2               | 98%       |
| 500   | 50         | 500             | 10              | 98%       |

---

## Response Format

All endpoints return `BatchProcessingResponse`:

```json
{
  "total_files": 100,
  "already_processed_count": 20,
  "processed_files": 80,
  "successful_files": 75,
  "failed_files": 5,
  "results": [
    {
      "file_key": "uploads/invoice-123.pdf",
      "filename": "invoice-123.pdf",
      "status": "completed",
      "file_hash": "abc123...",
      "p7m_file_key": "signed/invoice-123.pdf.p7m",
      "processing_time": 1.23,
      "error_message": null
    }
  ],
  "processing_start": "2025-01-31T10:00:00Z",
  "processing_end": "2025-01-31T10:05:00Z",
  "duration_seconds": 300.0,
  "message": "75 files successfully processed. 5 files failed."
}
```

---

## When to Use Which Endpoint

### Use `/process` when:
- Processing monthly batches of new files
- You have a specific date range of uploads
- You want to skip already-processed files
- You need smart, efficient processing

### Use `/reprocess-failed` when:
- Files failed due to network issues
- API was temporarily unavailable
- You want to retry all failures from a month
- You need to fix specific failed files

### Use `/resign` when:
- You need fresh timestamps on files
- Certificate was renewed and you need new signatures
- Files need to be re-certified for compliance
- You want to force re-signing regardless of current state

---

## Error Handling

All endpoints use **continue-on-error** behavior:
- ✅ Individual file failures don't stop batch processing
- ✅ Failed files saved to DynamoDB with error details
- ✅ Detailed error messages in response
- ✅ SNS notifications with batch statistics

---

## Best Practices

1. **For monthly processing**: Use `/process` with date range
2. **For failure recovery**: Use `/reprocess-failed` with date partition
3. **For targeted re-signing**: Use `/resign` with specific file keys
4. **Monitor failures**: Check `/failed-files` endpoint regularly
5. **Review logs**: All endpoints provide detailed logging with correlation IDs

---

## Integration Examples

### Python Client

```python
import requests

# Process files from January 2025
response = requests.post(
    "http://localhost:8000/process",
    json={
        "start_date": "2025-01-01T00:00:00Z",
        "end_date": "2025-01-31T23:59:59Z"
    }
)
result = response.json()
print(f"Processed: {result['successful_files']}/{result['total_files']}")

# Reprocess failed files from January
response = requests.post(
    "http://localhost:8000/reprocess-failed",
    json={"date_partition": "2025-01"}
)

# Re-sign specific files
response = requests.post(
    "http://localhost:8000/resign",
    json={
        "file_keys": [
            "uploads/invoice-123.pdf",
            "uploads/invoice-456.pdf"
        ]
    }
)
```

### cURL Examples

```bash
# Process files
curl -X POST "http://localhost:8000/process" \
  -H "Content-Type: application/json" \
  -d '{"start_date": "2025-01-01T00:00:00Z", "end_date": "2025-01-31T23:59:59Z"}'

# Reprocess failures
curl -X POST "http://localhost:8000/reprocess-failed" \
  -H "Content-Type: application/json" \
  -d '{"date_partition": "2025-01"}'

# Re-sign files
curl -X POST "http://localhost:8000/resign" \
  -H "Content-Type: application/json" \
  -d '{"file_keys": ["uploads/invoice-123.pdf"]}'
```

---

## Documentation

All endpoints are documented in:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **OpenAPI Spec**: http://localhost:8000/openapi.json
