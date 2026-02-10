# Amazon Cognito OAuth2 Token Proxy with Caching

This solution provides an API Gateway proxy in front of Amazon Cognito's OAuth2 token endpoint, adding intelligent caching and API key-based access control to reduce load on Cognito and improve performance for machine-to-machine (M2M) authentication scenarios.

## Table of Contents

- [Architecture](#architecture)
- [Features](#features)
- [Prerequisites](#prerequisites)
- [Deployment](#deployment)
  - [Cost Considerations](#cost-considerations)
  - [Deploy with AWS CDK](#deploy-with-aws-cdk)
  - [Deploy with CloudFormation](#deploy-with-cloudformation)
- [Usage](#usage)
  - [Authentication Methods](#authentication-methods)
  - [Testing the Deployment](#testing-the-deployment)
- [Security](#security)
- [Monitoring](#monitoring)
- [Cleanup](#cleanup)
- [Additional Resources](#additional-resources)
- [Contributing](#contributing)
- [License](#license)

## Architecture

The solution deploys an Amazon API Gateway REST API that proxies requests to Amazon Cognito's OAuth2 token endpoint. The proxy adds a caching layer to reduce latency and Cognito API calls, and requires API key authentication for access control.

![Architecture Diagram](docs/images/architecture-diagram.png)

### Components

- **Amazon API Gateway**: Regional REST API with `/oauth2/token` endpoint
- **API Gateway Cache**: Configurable cache (0.5GB - 237GB) with TTL-based expiration
- **API Key**: Required for all requests to the proxy endpoint
- **AWS WAF (Optional)**: WebACL that validates API key before allowing direct Cognito access
- **Amazon Cognito User Pool**: OAuth2 token endpoint for client credentials flow
- **AWS Lambda**: Custom resource to retrieve API key value for WAF configuration

### User Flow

1. Client application sends OAuth2 token request to API Gateway with API key
2. API Gateway checks cache for existing valid token
3. On cache miss, API Gateway forwards request to Cognito
4. Cognito validates credentials and returns access token
5. API Gateway caches response and returns token to client
6. Subsequent requests with same credentials return cached token (cache hit)

## Features

- **Token Caching**: Reduces Cognito API calls and improves response times
- **Cost Optimization**: Minimizes Cognito usage costs through intelligent caching
- **API Key Protection**: Adds security layer requiring valid API key for all requests
- **WAF Integration**: Optional WAF protection prevents unauthorized direct Cognito access
- **Flexible Authentication**: Supports Authorization header, query parameters, or request body
- **Encrypted Cache**: Cache data encrypted at rest
- **Multiple Cache Sizes**: Choose from 0.5GB to 237GB based on your needs

## Prerequisites

Before you deploy this solution, you must have the following:

- An AWS account
- An Amazon Cognito User Pool with OAuth2 client credentials configured
- A Cognito domain (Amazon Cognito domain or custom domain)
- AWS CLI version 2.x or later, configured with appropriate credentials
- For CDK deployment:
  - Python 3.8 or later
  - Node.js 20.x or later
  - AWS CDK CLI 2.x (`npm install -g aws-cdk`)

## Deployment

### Cost Considerations

You are responsible for the cost of the AWS services used while running this solution. There is no additional cost for using this solution. For full details, see the pricing pages for each AWS service you use in this solution:

- [Amazon API Gateway pricing](https://aws.amazon.com/api-gateway/pricing/)
- [Amazon Cognito pricing](https://aws.amazon.com/cognito/pricing/)
- [AWS WAF pricing](https://aws.amazon.com/waf/pricing/) (if WAF protection is enabled)
- [AWS Lambda pricing](https://aws.amazon.com/lambda/pricing/) (for custom resource)

Prices are subject to change.

### Deploy with AWS CDK

The AWS CDK implementation is the recommended deployment method as it provides better type safety, maintainability, and follows AWS best practices.

#### Step 1: Clone the repository

```bash
git clone https://github.com/josemiguel100/cognito-m2m-token-cache-on-aws.git
cd cognito-m2m-token-cache-on-aws
```

#### Step 2: Set up the Python virtual environment

```bash
cd cdk
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

#### Step 3: Configure deployment parameters

Create a deployment script with your configuration:

```bash
#!/bin/bash
cdk deploy \
  --profile YOUR_AWS_PROFILE \
  -c cognito_domain=YOUR_COGNITO_DOMAIN.auth.REGION.amazoncognito.com \
  -c cognito_user_pool_arn=arn:aws:cognito-idp:REGION:ACCOUNT:userpool/POOL_ID \
  -c stage_name=dev \
  -c cache_ttl_seconds=3600 \
  -c cache_size_gb=0.5 \
  -c enable_waf_protection=true \
  --outputs-file ../cdk-outputs.json
```

Replace the following values:
- `YOUR_AWS_PROFILE`: Your AWS CLI profile name
- `YOUR_COGNITO_DOMAIN`: Your Cognito domain without `https://`
- `REGION`: Your AWS region (for example, `us-east-1`)
- `ACCOUNT`: Your AWS account ID
- `POOL_ID`: Your Cognito User Pool ID

#### Step 4: Deploy the stack

```bash
chmod +x deploy.sh
./deploy.sh
```

The deployment takes approximately 2-3 minutes. After deployment completes, the stack outputs include:
- `ApiEndpointOutput`: The API Gateway endpoint URL
- `ProxyAPIKeyOutput`: The API key ID (retrieve the value from API Gateway console)
- `WebACLOutput`: The WAF WebACL ARN (if WAF protection is enabled)

**Note**: If you enable WAF protection, the WAF association with Cognito may take 5-10 minutes to propagate after deployment.

### Deploy with CloudFormation

You can also deploy using the CloudFormation template directly.

#### Step 1: Validate the template

```bash
aws cloudformation validate-template \
  --template-body file://cognito-proxy-template.yaml \
  --profile YOUR_AWS_PROFILE
```

#### Step 2: Deploy the stack

```bash
aws cloudformation deploy \
  --template-file cognito-proxy-template.yaml \
  --stack-name cognito-oauth-proxy \
  --parameter-overrides \
    CognitoDomain=YOUR_COGNITO_DOMAIN.auth.REGION.amazoncognito.com \
    StageName=dev \
    CacheTtlInSeconds=3600 \
    CacheSize=0.5 \
  --profile YOUR_AWS_PROFILE
```

#### Step 3: Get stack outputs

```bash
aws cloudformation describe-stacks \
  --stack-name cognito-oauth-proxy \
  --query 'Stacks[0].Outputs' \
  --profile YOUR_AWS_PROFILE
```

## Usage

### Authentication Methods

The proxy supports three methods for providing OAuth2 credentials:

#### Method 1: Authorization Header (Recommended)

```bash
curl -X POST https://API_ID.execute-api.REGION.amazonaws.com/STAGE/oauth2/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -H "x-api-key: YOUR_API_KEY" \
  -H "Authorization: Basic $(echo -n 'CLIENT_ID:CLIENT_SECRET' | base64)" \
  -d "grant_type=client_credentials&scope=your/scope"
```

#### Method 2: Request Body Parameters

```bash
curl -X POST https://API_ID.execute-api.REGION.amazonaws.com/STAGE/oauth2/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -H "x-api-key: YOUR_API_KEY" \
  -d "grant_type=client_credentials&client_id=CLIENT_ID&client_secret=CLIENT_SECRET&scope=your/scope"
```

#### Method 3: Query Parameters

```bash
curl -X POST "https://API_ID.execute-api.REGION.amazonaws.com/STAGE/oauth2/token?client_id=CLIENT_ID&client_secret=CLIENT_SECRET&scope=your/scope" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -H "x-api-key: YOUR_API_KEY" \
  -d "grant_type=client_credentials"
```

### Response Format

Successful requests return a JSON response:

```json
{
  "access_token": "eyJraWQiOiJ...",
  "expires_in": 3600,
  "token_type": "Bearer"
}
```

### Testing the Deployment

For comprehensive testing instructions, including tests for API Gateway with and without API keys, and WAF protection validation, see the [Testing Guide](docs/testing-guide.md).

## Security

This solution implements multiple security layers:

1. **API Key Authentication**: All requests to the API Gateway endpoint require a valid `x-api-key` header
2. **HTTPS Only**: All traffic is encrypted in transit using TLS
3. **Encrypted Cache**: Cached tokens are encrypted at rest
4. **Regional Endpoint**: Reduces latency and keeps traffic within your AWS region
5. **WAF Protection** (Optional): When enabled, AWS WAF validates the API key before allowing requests to reach Cognito
   - Blocks unauthorized direct access to the Cognito User Pool
   - Returns descriptive error message for blocked requests
   - Automatically configured with the correct API key value during deployment

### Best Practices

- Rotate API keys regularly
- Use AWS Secrets Manager or AWS Systems Manager Parameter Store to store API keys
- Enable AWS CloudTrail logging for API Gateway
- Monitor API Gateway metrics in Amazon CloudWatch
- Set appropriate cache TTL based on your token expiration time
- Enable WAF protection to prevent direct Cognito access

## Monitoring

Monitor the solution using Amazon CloudWatch metrics:

- **CacheHitCount / CacheMissCount**: Measure cache effectiveness
- **Count**: Total number of requests
- **Latency**: Response times
- **4XXError / 5XXError**: Error rates

To view metrics:

```bash
aws cloudwatch get-metric-statistics \
  --namespace AWS/ApiGateway \
  --metric-name CacheHitCount \
  --dimensions Name=ApiName,Value=CognitoAuthProxy \
  --start-time 2024-01-01T00:00:00Z \
  --end-time 2024-01-01T23:59:59Z \
  --period 3600 \
  --statistics Sum \
  --profile YOUR_AWS_PROFILE
```

## Cleanup

To avoid incurring future charges, delete the resources created by this solution.

### Delete CDK Stack

```bash
cd cdk
cdk destroy --profile YOUR_AWS_PROFILE
```

### Delete CloudFormation Stack

```bash
aws cloudformation delete-stack \
  --stack-name cognito-oauth-proxy \
  --profile YOUR_AWS_PROFILE
```

**Note**: If you enabled WAF protection, you may need to manually disassociate the WAF WebACL from the Cognito User Pool before deletion:

```bash
aws wafv2 disassociate-web-acl \
  --resource-arn arn:aws:cognito-idp:REGION:ACCOUNT:userpool/POOL_ID \
  --profile YOUR_AWS_PROFILE \
  --region REGION
```

## Additional Resources

- [Amazon API Gateway Developer Guide](https://docs.aws.amazon.com/apigateway/)
- [Amazon Cognito Developer Guide](https://docs.aws.amazon.com/cognito/)
- [AWS WAF Developer Guide](https://docs.aws.amazon.com/waf/)
- [AWS CDK Developer Guide](https://docs.aws.amazon.com/cdk/)
- [OAuth 2.0 Client Credentials Grant](https://oauth.net/2/grant-types/client-credentials/)

## Contributing

Contributions are welcome! Please read the [CONTRIBUTING.md](CONTRIBUTING.md) file for guidelines on how to contribute to this project.

## License

This library is licensed under the MIT-0 License. See the [LICENSE](LICENSE) file for details.
