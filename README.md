# Amazon Cognito OAuth2 Token Proxy with Caching

An Amazon API Gateway proxy for Amazon Cognito's OAuth2 token endpoint that adds intelligent caching and API key-based access control, reducing costs, improving performance, and scaling machine-to-machine (M2M) authentication scenarios.

This repository provides a deployable implementation of the architecture described in the AWS Security Blog post: [How to monitor, optimize, and secure Amazon Cognito machine-to-machine authorization](https://aws.amazon.com/blogs/security/how-to-monitor-optimize-and-secure-amazon-cognito-machine-to-machine-authorization/).

## Table of Contents

- [Architecture](#architecture)
  - [Full Architecture](#full-architecture)
  - [Request Flow Without WAF](#request-flow-without-waf)
  - [Request Flow With WAF Protection](#request-flow-with-waf-protection)
  - [Components](#components)
- [Usage](#usage)
  - [Authentication Methods](#authentication-methods)
  - [Response Format](#response-format)
  - [Testing](#testing)
  - [Monitoring](#monitoring)
  - [Security Best Practices](#security-best-practices)
- [Prerequisites](#prerequisites)
- [Deployment](#deployment)
  - [Deploy with AWS CDK (Recommended)](#deploy-with-aws-cdk-recommended)
  - [Deploy with CloudFormation](#deploy-with-cloudformation)
- [Accessing the Application](#accessing-the-application)
- [Remove the Application](#remove-the-application)
- [Contributing](#contributing)
- [License](#license)

## Architecture

The solution deploys an Amazon API Gateway REST API that proxies requests to Amazon Cognito's OAuth2 token endpoint. The proxy adds a caching layer to reduce latency and Cognito API calls, and requires API key authentication for access control.

### Full Architecture

![Full Architecture](docs/images/architecture-overview.png)

The architecture consists of three main components working together. Client applications send OAuth2 token requests to an Amazon API Gateway REST API (Regional endpoint), which acts as a proxy in front of Amazon Cognito. API Gateway enforces API key validation on every incoming request through a usage plan, ensuring only authorized consumers can access the token endpoint. Before forwarding a request to Cognito, API Gateway checks its built-in response cache, keyed on the Authorization header. On a cache hit, the cached token is returned immediately without contacting Cognito, reducing both latency and cost. On a cache miss, API Gateway forwards the client credentials grant request to the Cognito User Pool's `/oauth2/token` endpoint, caches the response for the configured TTL, and returns the token to the caller. The entire infrastructure is defined and provisioned through a CloudFormation stack (deployable via AWS CDK or the CloudFormation template directly).

#### Cost Reduction Example

Consider an application that requests a new access token every 5 minutes (12 times per hour). With a 1-hour token expiration and this caching solution:

- **Without caching**: 12 Cognito API calls per hour = 288 calls per day per application
- **With caching**: 1 Cognito API call per hour = 24 calls per day per application
- **Reduction**: 91.7% fewer Cognito API calls

For 100 applications making similar requests:
- **Without caching**: 28,800 Cognito calls per day
- **With caching**: 2,400 Cognito calls per day
- **Monthly savings**: ~792,000 fewer Cognito API calls

At Cognito's pricing of $0.0055 per API call (after free tier), this represents significant cost savings while also improving response times through cache hits (typically <10ms vs 100-200ms for Cognito calls).

### Request Flow Without WAF

![Architecture Diagram](docs/images/architecture-diagram.png)

1. **Client Application** sends an OAuth2 token request to the API Gateway endpoint with an API key
2. **API Gateway** validates the API key and checks its cache for a valid token
3. **Cache Hit**: If a valid cached token exists, API Gateway returns it immediately (typically <10ms)
4. **Cache Miss**: If no cached token exists, API Gateway forwards the request to Cognito
5. **Amazon Cognito** validates the client credentials and returns an access token
6. **API Gateway** caches the token based on the Authorization header and returns it to the client
7. Subsequent requests with the same credentials receive the cached token until TTL expires

### Request Flow With WAF Protection

![Architecture with WAF](docs/images/architecture-with-waf.png)

When WAF protection is enabled, an additional security layer is added:

1. **AWS WAF WebACL** is associated with the Cognito User Pool
2. **Direct Cognito Access** is blocked by default unless the request includes the correct API key
3. **API Gateway** forwards requests to Cognito with the API key header
4. **WAF Validation** checks the `x-api-key` header value before allowing the request to reach Cognito
5. **Unauthorized Requests** receive a 403 Forbidden response with a descriptive error message
6. **Authorized Requests** (with correct API key) proceed to Cognito for token generation

This ensures that only requests through API Gateway (with valid API key) can access Cognito, preventing direct access and enforcing centralized access control.

### Components

- **Amazon API Gateway**: Regional REST API with `/oauth2/token` endpoint that proxies requests to Cognito
- **API Gateway Cache**: Configurable cache cluster (0.5GB - 237GB) with TTL-based expiration for storing tokens
- **API Key**: Required for all requests to the proxy endpoint, managed through API Gateway usage plans
- **AWS WAF (Optional)**: WebACL that validates API key before allowing direct Cognito access
- **Amazon Cognito User Pool**: OAuth2 token endpoint for client credentials flow
- **AWS Lambda**: Custom resource function to retrieve API key value for WAF configuration during deployment
- **CloudWatch Logs**: Access logging for API Gateway requests
- **AWS X-Ray**: Distributed tracing for request monitoring

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

### Testing

For comprehensive testing instructions, including tests for API Gateway with and without API keys, and WAF protection validation, see the [Testing Guide](docs/testing-guide.md).

### Monitoring

Monitor the solution using Amazon CloudWatch metrics:

- **CacheHitCount / CacheMissCount**: Measure cache effectiveness
- **Count**: Total number of requests
- **Latency**: Response times
- **4XXError / 5XXError**: Error rates

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

### Security Best Practices

This solution implements multiple security layers: API key authentication, HTTPS-only traffic, encrypted cache at rest, regional endpoints, optional WAF protection, access logging, and X-Ray tracing.

- Rotate API keys regularly
- Use AWS Secrets Manager or AWS Systems Manager Parameter Store to store API keys
- Enable AWS CloudTrail logging for API Gateway
- Monitor API Gateway metrics in Amazon CloudWatch
- Set appropriate cache TTL based on your token expiration time
- Enable WAF protection to prevent direct Cognito access

## Prerequisites

Before you deploy this solution, you must have the following:

- An [AWS account](https://aws.amazon.com/premiumsupport/knowledge-center/create-and-activate-aws-account/)
- An Amazon Cognito User Pool with OAuth2 client credentials configured
- A Cognito domain (Amazon Cognito domain or custom domain)
- [AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html) version 2.x or later, configured with appropriate credentials
- For CDK deployment:
  - [Python](https://www.python.org/downloads/) >= 3.8
  - [Node.js](https://nodejs.org/) >= 20.x
  - [AWS CDK CLI](https://docs.aws.amazon.com/cdk/v2/guide/getting-started.html) >= 2.x (`npm install -g aws-cdk`)

## Deployment

> **Important**: You are responsible for the cost of the AWS services used while running this sample deployment. There is no additional cost for using this sample. For full details, see the pricing pages for each AWS service you will be using in this sample. Prices are subject to change.
>
> - [Amazon API Gateway pricing](https://aws.amazon.com/api-gateway/pricing/)
> - [Amazon Cognito pricing](https://aws.amazon.com/cognito/pricing/)
> - [AWS WAF pricing](https://aws.amazon.com/waf/pricing/) (if WAF protection is enabled)
> - [AWS Lambda pricing](https://aws.amazon.com/lambda/pricing/) (for custom resource)

### Deploy with AWS CDK (Recommended)

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
  --capabilities CAPABILITY_IAM \
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

## Accessing the Application

After deployment, retrieve the API endpoint and API key from the stack outputs:

1. The `ApiEndpointOutput` provides the URL: `https://<API_ID>.execute-api.<REGION>.amazonaws.com/<STAGE>/oauth2/token`
2. Retrieve the API key value from the API Gateway console or via CLI:

```bash
aws apigateway get-api-keys --include-values --profile YOUR_AWS_PROFILE
```

3. Send a token request using any of the [authentication methods](#authentication-methods) described above.

For detailed testing scenarios, see the [Testing Guide](docs/testing-guide.md).

## Remove the Application

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

## Contributing

Contributions are welcome! Please read the [CONTRIBUTING.md](CONTRIBUTING.md) file for guidelines on how to contribute to this project.

## License

This library is licensed under the MIT-0 License. See the [LICENSE](LICENSE) file for details.
