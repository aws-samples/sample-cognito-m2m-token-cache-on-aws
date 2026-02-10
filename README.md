# Cognito OAuth2 Token Proxy with API Gateway Caching

## Overview

This project provides both CloudFormation and AWS CDK (Python) implementations of an API Gateway proxy in front of AWS Cognito's OAuth2 token endpoint. The proxy adds intelligent caching and API key-based access control, reducing load on Cognito and improving performance for machine-to-machine (M2M) authentication scenarios.

**Recommended**: Use the CDK implementation in the `cdk/` directory for better maintainability and type safety.

## Purpose

The proxy solves several challenges with direct Cognito OAuth2 token requests:

- **Performance**: Caches OAuth2 tokens to reduce latency and Cognito API calls
- **Cost Optimization**: Reduces Cognito usage costs through intelligent caching
- **Access Control**: Adds API key requirement for additional security layer
- **WAF Protection**: Optional WAF WebACL that validates API key before allowing Cognito access
- **Flexibility**: Supports multiple authentication methods (Authorization header, query params, or body params)

## Architecture

```
Client Application
       ↓
   [API Key Required]
       ↓
API Gateway Proxy (/oauth2/token)
       ↓
   [Cache Layer]
       ↓
   [WAF WebACL - Optional]
       ↓
AWS Cognito OAuth2 Endpoint
```

### Key Features

1. **Caching**: Configurable cache (0.5GB - 237GB) with TTL (default 1 hour)
2. **Cache Key**: Based on Authorization header for per-client caching
3. **API Key Protection**: All requests require valid API key
4. **WAF Protection**: Optional WAF WebACL validates API key before allowing Cognito access
5. **Multiple Auth Methods**: Supports Authorization header, query parameters, or request body
6. **Scope Support**: Handles OAuth2 scopes in requests
7. **Encrypted Cache**: Cache data is encrypted at rest

## Project Structure

```
.
├── README.md                                    # This file
├── cognito-proxy-template.yaml                  # CloudFormation template (legacy)
├── cdk/                                         # CDK Python implementation
│   ├── app.py                                   # CDK app entry point
│   ├── cdk/
│   │   ├── __init__.py
│   │   └── cognito_proxy_stack.py               # Main stack definition
│   ├── tests/                                   # CDK tests
│   ├── requirements.txt                         # Python dependencies
│   ├── cdk.json                                 # CDK configuration
│   └── README.md                                # CDK-specific documentation
├── .kiro/
│   └── steering/                                # Project steering documents
│       ├── project-overview.md
│       └── aws-guidelines.md
├── architecturediagrams/
│   ├── CognitoM2MArchitecture-Page-1.drawio.png
│   ├── CognitoM2MArchitecture-Page-2.drawio.png
│   └── CognitoM2MArchitecture.drawio
├── testcommands.txt                             # Legacy test commands
└── test-instructions.txt                        # Comprehensive testing guide with WAF tests
```

## Prerequisites

- AWS CLI configured with `Cognito-Isengard6` profile
- AWS Cognito User Pool with OAuth2 client credentials configured
- Cognito domain (either Amazon Cognito domain or custom domain)

## CloudFormation Parameters

| Parameter | Description | Default | Required |
|-----------|-------------|---------|----------|
| `CognitoDomain` | Cognito domain WITHOUT https:// (e.g., your-domain.auth.region.amazoncognito.com) | - | Yes |
| `StageName` | API Gateway deployment stage name | `dev` | No |
| `CacheTtlInSeconds` | Cache TTL in seconds | `3600` (1 hour) | No |
| `CacheSize` | Cache cluster size in GB | `0.5` | No |

### Cache Size Options
- 0.5, 1.6, 6.1, 13.5, 28.4, 58.2, 118, 237 GB

## Deployment

### Option 1: CDK Deployment (Recommended)

The CDK implementation provides better type safety, maintainability, and follows AWS best practices.

#### Prerequisites
- Python 3.8+
- AWS CDK CLI: `npm install -g aws-cdk`
- AWS CLI configured with `Cognito-Isengard6` profile

#### Setup

```bash
cd cdk
source .venv/bin/activate
pip install -r requirements.txt
```

#### Deploy

Create a deployment script or use the command directly:

```bash
cd cdk
cdk deploy \
  --profile Cognito-Isengard6 \
  -c cognito_domain=YOUR_COGNITO_DOMAIN.auth.REGION.amazoncognito.com \
  -c cognito_user_pool_arn=arn:aws:cognito-idp:REGION:ACCOUNT:userpool/POOL_ID \
  -c stage_name=dev \
  -c cache_ttl_seconds=3600 \
  -c cache_size_gb=0.5 \
  -c enable_waf_protection=true \
  --outputs-file ../cdk-outputs.json
```

**Parameters**:
- `cognito_domain`: Your Cognito domain (required)
- `cognito_user_pool_arn`: ARN of your Cognito User Pool (required if WAF enabled)
- `stage_name`: API Gateway stage (default: dev)
- `cache_ttl_seconds`: Cache TTL in seconds (default: 3600)
- `cache_size_gb`: Cache size in GB (default: 0.5)
- `enable_waf_protection`: Enable WAF WebACL protection (default: false)

**Note**: Create local deployment scripts (`deploy-cdk.sh` or `deployment-commands.txt`) with your specific configuration. These files are gitignored to avoid committing sensitive domain information.

#### View Outputs

After deployment:

```bash
aws cloudformation describe-stacks \
  --stack-name CognitoProxyStack \
  --profile Cognito-Isengard6 \
  --query 'Stacks[0].Outputs' \
  --output table
```

Or check the generated `cdk-outputs.json` file.

See `cdk/README.md` for detailed CDK documentation.

### Option 2: CloudFormation Template

#### Validate Template

```bash
aws cloudformation validate-template \
  --template-body file://cognito-proxy-template.yaml \
  --profile Cognito-Isengard6
```

### Deploy Stack

```bash
aws cloudformation deploy \
  --template-file cognito-proxy-template.yaml \
  --stack-name cognito-oauth-proxy \
  --parameter-overrides \
    CognitoDomain=your-domain.auth.us-east-1.amazoncognito.com \
    StageName=dev \
    CacheTtlInSeconds=3600 \
    CacheSize=0.5 \
  --profile Cognito-Isengard6
```

### Get Stack Outputs

```bash
aws cloudformation describe-stacks \
  --stack-name cognito-oauth-proxy \
  --query 'Stacks[0].Outputs' \
  --profile Cognito-Isengard6
```

## Usage

### Authentication Methods

The proxy supports three authentication methods:

#### 1. Authorization Header (Recommended)

```bash
curl -X POST https://{api-id}.execute-api.{region}.amazonaws.com/dev/oauth2/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -H "x-api-key: YOUR_API_KEY" \
  -H "Authorization: Basic $(echo -n 'CLIENT_ID:CLIENT_SECRET' | base64)" \
  -d "grant_type=client_credentials&scope=your/scope"
```

#### 2. Request Body Parameters

```bash
curl -X POST https://{api-id}.execute-api.{region}.amazonaws.com/dev/oauth2/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -H "x-api-key: YOUR_API_KEY" \
  -d "grant_type=client_credentials&client_id=CLIENT_ID&client_secret=CLIENT_SECRET&scope=your/scope"
```

#### 3. Query Parameters

```bash
curl -X POST "https://{api-id}.execute-api.{region}.amazonaws.com/dev/oauth2/token?client_id=CLIENT_ID&client_secret=CLIENT_SECRET&scope=your/scope" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -H "x-api-key: YOUR_API_KEY" \
  -d "grant_type=client_credentials"
```

### Response

```json
{
  "access_token": "eyJraWQiOiJ...",
  "expires_in": 3600,
  "token_type": "Bearer"
}
```

## Stack Outputs

| Output | Description |
|--------|-------------|
| `ApiEndpoint` | Full URL to the OAuth2 token proxy endpoint |
| `ProxyAPIKey` | API Key ID (retrieve value from API Gateway console) |
| `CacheClusterSize` | Configured cache size |
| `CacheTtl` | Configured cache TTL in seconds |

## Resources Created

- **API Gateway REST API**: Regional endpoint with `/oauth2/token` path
- **API Key**: For request authentication
- **Usage Plan**: Links API key to the API stage
- **Cache Cluster**: For token response caching
- **API Gateway Stage**: Deployment stage with caching enabled
- **Lambda Function**: Custom resource to retrieve API key value (when WAF enabled)
- **WAF WebACL**: Validates API key before allowing Cognito access (optional)
- **WAF Association**: Links WebACL to Cognito User Pool (when WAF enabled)

## Caching Behavior

- **Cache Key**: Based on the `Authorization` header (per-client caching)
- **Cache Scope**: Only `/oauth2/token` POST requests are cached
- **Encryption**: Cache data is encrypted at rest
- **TTL**: Configurable (default 1 hour)
- **Cache Miss**: Proxies request to Cognito and caches response
- **Cache Hit**: Returns cached token without calling Cognito

## Security Considerations

1. **API Key Required**: All requests must include valid `x-api-key` header
2. **HTTPS Only**: All traffic is encrypted in transit
3. **Encrypted Cache**: Cached tokens are encrypted at rest
4. **Regional Endpoint**: Reduces latency and keeps traffic within region
5. **WAF Protection**: Optional WAF WebACL validates API key before allowing direct Cognito access
   - Prevents unauthorized direct access to Cognito User Pool
   - Only requests with the correct API key can reach Cognito
   - WAF rule automatically configured with API key value during deployment
   - Returns custom error message: "WAF is preventing direct access to Cognito. Please use the API Gateway endpoint with a valid API key."
   - WAF associations may take 5-10 minutes to propagate after deployment

## Monitoring

Monitor the proxy using CloudWatch metrics:

- `CacheHitCount` / `CacheMissCount`: Cache effectiveness
- `Count`: Total requests
- `Latency`: Response times
- `4XXError` / `5XXError`: Error rates

## Cost Considerations

- API Gateway requests (reduced by caching)
- Cache cluster (based on size selected)
- Data transfer
- Cognito token requests (significantly reduced by caching)

## Troubleshooting

### Common Issues

1. **Invalid API Key**: Ensure `x-api-key` header is included
2. **Cache Not Working**: Verify Authorization header is consistent
3. **Cognito Errors**: Check Cognito domain parameter is correct
4. **403 Forbidden**: Verify API key is associated with usage plan
5. **WAF Not Blocking**: WAF associations can take 5-10 minutes to propagate after deployment

### Testing

See `test-instructions.txt` for comprehensive test commands including:
- API Gateway requests with and without API keys
- Direct Cognito access tests to verify WAF protection
- Expected responses for each scenario

## Development

### AWS CLI Profile

All AWS CLI commands must use the `Cognito-Isengard6` profile:

```bash
aws <service> <command> --profile Cognito-Isengard6
```

### Template Modifications

When modifying the CloudFormation template:

1. Validate changes locally
2. Test in non-production environment first
3. Update this README with any new parameters or outputs
4. Update architecture diagrams if architecture changes

## References

- Architecture diagrams: `architecturediagrams/`
- Blog posts and guides: `blog/`
- Original template: `originaltemplate/`
- Test commands: `testcommands.txt`

## License

[Add license information]

## Contributors

[Add contributor information]
