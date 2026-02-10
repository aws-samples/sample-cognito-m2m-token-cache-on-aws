# Cognito OAuth2 Token Proxy - CDK Implementation

This directory contains the AWS CDK (Python) implementation of the Cognito OAuth2 Token Proxy.

## Prerequisites

- Python 3.8 or later
- AWS CDK CLI installed (`npm install -g aws-cdk`)
- AWS CLI configured with `Cognito-Isengard6` profile
- Virtual environment activated

## Setup

1. Activate the virtual environment:

```bash
source .venv/bin/activate
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

## Configuration

The stack accepts the following parameters via CDK context:

| Parameter | Description | Required | Default |
|-----------|-------------|----------|---------|
| `cognito_domain` | Cognito domain WITHOUT https:// | Yes | - |
| `stage_name` | API Gateway stage name | No | `dev` |
| `cache_ttl_seconds` | Cache TTL in seconds | No | `3600` |
| `cache_size_gb` | Cache size in GB | No | `0.5` |

Valid cache sizes: 0.5, 1.6, 6.1, 13.5, 28.4, 58.2, 118, 237

## CDK Commands

### Synthesize CloudFormation Template

```bash
cdk synth -c cognito_domain=your-domain.auth.us-east-1.amazoncognito.com
```

### Deploy Stack

```bash
cdk deploy \
  --profile Cognito-Isengard6 \
  -c cognito_domain=your-domain.auth.us-east-1.amazoncognito.com \
  -c stage_name=dev \
  -c cache_ttl_seconds=3600 \
  -c cache_size_gb=0.5
```

### Diff Against Deployed Stack

```bash
cdk diff --profile Cognito-Isengard6 -c cognito_domain=your-domain.auth.us-east-1.amazoncognito.com
```

### Destroy Stack

```bash
cdk destroy --profile Cognito-Isengard6
```

### List Stacks

```bash
cdk ls
```

## Stack Outputs

After deployment, the stack provides:

- `ApiEndpoint`: Full URL to the OAuth2 token proxy endpoint
- `ProxyAPIKey`: API Key ID (retrieve value from AWS Console)
- `CacheClusterSize`: Configured cache size
- `CacheTtl`: Configured cache TTL in seconds

## Project Structure

```
cdk/
├── app.py                      # CDK app entry point
├── cdk/
│   ├── __init__.py
│   └── cognito_proxy_stack.py  # Main stack definition
├── tests/
│   └── unit/
│       └── test_cdk_stack.py   # Unit tests
├── requirements.txt            # Python dependencies
├── requirements-dev.txt        # Development dependencies
├── cdk.json                    # CDK configuration
└── README.md                   # This file
```

## Stack Resources

The CDK stack creates:

1. **API Gateway REST API**: Regional endpoint with `/oauth2/token` path
2. **API Key**: For request authentication
3. **Usage Plan**: Links API key to the API stage
4. **Cache Cluster**: For token response caching
5. **API Gateway Stage**: Deployment stage with caching enabled

## Development

### Running Tests

```bash
pytest
```

### Type Checking

```bash
mypy cdk/
```

## Comparison with CloudFormation

This CDK implementation provides the same functionality as `cognito-proxy-template.yaml` with these benefits:

- Type safety and IDE autocomplete
- Easier parameter validation
- More maintainable code structure
- Built-in best practices
- Simpler testing

## Notes

- The VTL (Velocity Template Language) request mapping template is preserved from the CloudFormation version
- Caching is configured only for the `/oauth2/token` POST endpoint
- Cache keys are based on the Authorization header for per-client caching
- All cache data is encrypted at rest
