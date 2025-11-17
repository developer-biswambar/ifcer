# Swagger/OpenAPI Configuration Guide

## Overview

The IFCER Batch Service now includes comprehensive Swagger UI and ReDoc documentation configuration.

## Accessing Documentation

Once the server is running, you can access the API documentation at:

- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`
- **OpenAPI Spec**: `http://localhost:8000/openapi.json`

## Configuration Details

### 1. Enhanced API Information

The FastAPI application (`app/main.py`) now includes:

- **Rich Description**: Detailed markdown description of the service
- **Version Information**: Automatically pulled from `app.__version__`
- **Contact Information**: Platform team contact details
- **License Information**: Proprietary license declaration
- **Terms of Service**: Link to terms (update as needed)

### 2. API Tags Organization

Three main API tag categories are defined:

#### **Processing**
Core processing endpoints for batch file certification, recertification, and reprocessing.

#### **Files**
File management endpoints for verifying P7M signatures, downloading signed files, and querying certification records.

#### **Certificates**
Certificate management endpoints for fetching and verifying InfoCert signing certificates.

### 3. Swagger UI Customization

The following Swagger UI parameters are configured:

```python
swagger_ui_parameters = {
    "defaultModelsExpandDepth": -1,      # Hide schemas section by default
    "docExpansion": "list",               # Expand only tags by default
    "filter": True,                       # Enable search/filter
    "syntaxHighlight.theme": "monokai",  # Code syntax highlighting
    "tryItOutEnabled": True,              # Enable "Try it out" by default
    "persistAuthorization": True,         # Persist auth between refreshes
}
```

**Features:**
- ✅ Clean interface with schemas hidden by default
- ✅ Search/filter functionality enabled
- ✅ Monokai syntax highlighting for better code readability
- ✅ "Try it out" enabled by default for testing
- ✅ Authorization persists across page refreshes

### 4. ReDoc Customization

The following ReDoc options are configured:

```python
redoc_options = {
    "hideDownloadButton": False,      # Show OpenAPI spec download button
    "expandResponses": "200,201",     # Auto-expand success responses
    "pathInMiddlePanel": True,        # Show path in middle panel
}
```

**Features:**
- ✅ Download OpenAPI specification button
- ✅ Success responses (200, 201) auto-expanded
- ✅ Enhanced path visibility

## Usage Examples

### Starting the Server

```bash
# Development mode with auto-reload
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Production mode
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

### Accessing Documentation

1. **Swagger UI** (Interactive API testing):
   - Navigate to: http://localhost:8000/docs
   - Use "Try it out" buttons to test endpoints
   - View request/response schemas
   - Test API calls directly from browser

2. **ReDoc** (Beautiful API documentation):
   - Navigate to: http://localhost:8000/redoc
   - Three-panel layout for easy navigation
   - Download OpenAPI spec
   - Search through documentation

3. **OpenAPI Specification**:
   - Download from: http://localhost:8000/openapi.json
   - Use with code generators (e.g., `openapi-generator`)
   - Import into Postman or other API clients

## Key Features in Documentation

### Processing Workflow Documentation

The main page includes a comprehensive workflow:

1. Upload files to S3 `uploads/` folder
2. Call `/process` endpoint with date range
3. Service downloads files, computes hashes, and sends to InfoCert
4. InfoCert returns digital signatures and timestamps
5. Service creates P7M files (PKCS#7 with embedded original file)
6. P7M files uploaded to S3 `signed/` folder
7. Metadata saved to DynamoDB

### Feature Highlights

- **Batch Processing**: Process multiple files efficiently using batch signing API
- **Smart Processing**: Skip already-processed files to avoid unnecessary API costs
- **Fail-Safe**: Continue-on-error behavior with detailed error tracking
- **CAdES-BES Compliance**: ETSI EN 319 122-1 compliant signatures
- **Timestamping**: RFC 3161 compliant timestamps from InfoCert TSA
- **S3 Integration**: Seamless file upload/download from AWS S3
- **DynamoDB Tracking**: Persistent certification records with optional TTL
- **mTLS Security**: Mutual TLS authentication with InfoCert API

### Authentication Documentation

All InfoCert API calls use:
- **mTLS**: Mutual TLS with client certificate
- **Bearer Token**: SAT (Signature Activation Token)
- **X-signer-id**: Credential ID header
- **PIN**: Signature PIN in request body

## Customization

### Updating Contact Information

Edit `app/main.py`:

```python
contact={
    "name": "Your Team Name",
    "email": "your-email@example.com",
}
```

### Updating Terms of Service

Edit `app/main.py`:

```python
terms_of_service="https://your-domain.com/terms"
```

### Changing Swagger UI Theme

Available themes:
- `"monokai"` (current)
- `"agate"`
- `"arta"`
- `"github"`
- `"tomorrow-night"`

Update in `app/main.py`:

```python
swagger_ui_parameters={
    "syntaxHighlight.theme": "github",  # Change theme here
    ...
}
```

### Adding More API Tags

Add to `tags_metadata` in `app/main.py`:

```python
tags_metadata = [
    {
        "name": "YourTag",
        "description": "Description of your tag group",
    },
]
```

## Files Modified

1. **app/main.py**
   - Enhanced OpenAPI configuration
   - Added comprehensive API description
   - Configured Swagger UI parameters
   - Configured ReDoc options
   - Added API tags metadata

2. **app/routers/certificates_routes.py**
   - Removed duplicate tag declaration (now centralized in main.py)

## Testing Documentation

1. Start the development server:
   ```bash
   uvicorn app.main:app --reload
   ```

2. Open your browser:
   - Swagger UI: http://localhost:8000/docs
   - ReDoc: http://localhost:8000/redoc

3. Verify:
   - ✅ All endpoints are visible
   - ✅ Tags are properly organized
   - ✅ Descriptions are rendered correctly
   - ✅ "Try it out" functionality works
   - ✅ Schemas are displayed properly

## Benefits

### For Developers
- Interactive API testing without external tools
- Clear request/response examples
- Schema validation information
- Quick prototyping and debugging

### For API Users
- Comprehensive documentation
- Clear endpoint descriptions
- Request/response examples
- Authentication requirements

### For Integration
- OpenAPI 3.x specification for code generation
- Postman/Insomnia import support
- Client SDK generation support
- API contract validation

## Next Steps

1. Review and update contact information
2. Update terms of service URL
3. Customize Swagger UI theme if desired
4. Add more detailed endpoint descriptions as needed
5. Consider adding example responses for complex endpoints

## Support

For questions or issues with the API documentation:
- Contact: IFCER Platform Team
- Email: support@example.com
