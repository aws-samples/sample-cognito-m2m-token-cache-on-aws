# Testing Guide

This guide provides comprehensive test commands to validate your Cognito OAuth2 Token Proxy deployment.

## Prerequisites

Before testing, ensure you have:
- Deployed the solution successfully via CDK
- Retrieved the API endpoint URL from stack outputs (`ApiEndpointOutput`)
- Your Cognito client credentials (client ID and client secret)
- Your Cognito domain (e.g., `your-prefix.auth.us-east-1.amazoncognito.com`)

## Test Scenarios

### Test 1: Token Request via API Gateway (Authorization Header)

Validates that the proxy returns a token when using the Authorization header method. Scope is passed in the request body.

**Expected Result**: ✓ Success — Returns OAuth2 access token

```bash
curl -X POST "https://API_ID.execute-api.REGION.amazonaws.com/STAGE/oauth2/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -H "Authorization: Basic $(echo -n 'CLIENT_ID:CLIENT_SECRET' | base64)" \
  -d "grant_type=client_credentials&scope=YOUR_SCOPE"
```

**Expected Response**:
```json
{
  "access_token": "eyJraWQiOiJ...",
  "expires_in": 3600,
  "token_type": "Bearer"
}
```

### Test 2: Token Request via API Gateway (Request Body)

Validates that the proxy returns a token when credentials and scope are passed in the request body.

**Expected Result**: ✓ Success — Returns OAuth2 access token

```bash
curl -X POST "https://API_ID.execute-api.REGION.amazonaws.com/STAGE/oauth2/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=client_credentials&client_id=CLIENT_ID&client_secret=CLIENT_SECRET&scope=YOUR_SCOPE"
```

### Test 3: Token Request via API Gateway (Query Parameters)

Validates that the proxy returns a token when credentials and scope are passed as query parameters. The scope value must be URL-encoded in the query string.

**Expected Result**: ✓ Success — Returns OAuth2 access token

```bash
curl -X POST "https://API_ID.execute-api.REGION.amazonaws.com/STAGE/oauth2/token?client_id=CLIENT_ID&client_secret=CLIENT_SECRET&scope=YOUR_URL_ENCODED_SCOPE" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=client_credentials"
```

**Note**: The scope must be URL-encoded when passed as a query parameter. For example, `https://my-api/read` becomes `https%3A%2F%2Fmy-api%2Fread`.

### Test 4: Direct Cognito Access (WAF Blocks)

Validates that WAF blocks direct access to Cognito, forcing clients through the API Gateway proxy.

**Expected Result**: ✗ Failure — 403 Forbidden

```bash
curl -X POST "https://YOUR_COGNITO_DOMAIN.auth.REGION.amazoncognito.com/oauth2/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -H "Authorization: Basic $(echo -n 'CLIENT_ID:CLIENT_SECRET' | base64)" \
  -d "grant_type=client_credentials&scope=YOUR_SCOPE"
```

**Expected Response**:
```json
{
  "message": "WAF is preventing direct access to Cognito. Please use the API Gateway endpoint."
}
```

**Note**: WAF associations may take 5-10 minutes to propagate after deployment. If this test initially succeeds, wait a few minutes and try again.

### Test 5: Cache Hit Validation

Validates that the API Gateway cache returns the same token on repeated requests.

1. Run the first request and note the `access_token` value and response time
2. Run the same request again immediately
3. The second request should return the exact same `access_token` and be faster (cache hit)

```bash
# First request (cache miss)
curl -s -w "\nTime: %{time_total}s\n" \
  -X POST "https://API_ID.execute-api.REGION.amazonaws.com/STAGE/oauth2/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -H "Authorization: Basic $(echo -n 'CLIENT_ID:CLIENT_SECRET' | base64)" \
  -d "grant_type=client_credentials&scope=YOUR_SCOPE"

# Second request (cache hit — same token, faster response)
curl -s -w "\nTime: %{time_total}s\n" \
  -X POST "https://API_ID.execute-api.REGION.amazonaws.com/STAGE/oauth2/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -H "Authorization: Basic $(echo -n 'CLIENT_ID:CLIENT_SECRET' | base64)" \
  -d "grant_type=client_credentials&scope=YOUR_SCOPE"
```

### Test 6: Scope-Based Cache Isolation

Validates that different scopes produce different cached tokens.

1. Request a token with scope A
2. Request a token with scope B (same credentials)
3. The tokens should be different (different `jti` claim)

```bash
# Request with scope A
curl -s -X POST "https://API_ID.execute-api.REGION.amazonaws.com/STAGE/oauth2/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -H "Authorization: Basic $(echo -n 'CLIENT_ID:CLIENT_SECRET' | base64)" \
  -d "grant_type=client_credentials&scope=SCOPE_A"

# Request with scope B (should return a different token)
curl -s -X POST "https://API_ID.execute-api.REGION.amazonaws.com/STAGE/oauth2/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -H "Authorization: Basic $(echo -n 'CLIENT_ID:CLIENT_SECRET' | base64)" \
  -d "grant_type=client_credentials&scope=SCOPE_B"
```

## Test Summary

| Test | Endpoint | Method | Expected Result |
|------|----------|--------|-----------------|
| 1 | API Gateway | Authorization header | ✓ Returns token |
| 2 | API Gateway | Request body | ✓ Returns token |
| 3 | API Gateway | Query parameters | ✓ Returns token |
| 4 | Direct Cognito | Any | ✗ 403 Forbidden (WAF blocks) |
| 5 | API Gateway | Repeated request | ✓ Same token, faster response |
| 6 | API Gateway | Different scopes | ✓ Different tokens per scope |

## Monitoring Cache Behavior

To verify cache hits in CloudWatch:

```bash
aws cloudwatch get-metric-statistics \
  --namespace AWS/ApiGateway \
  --metric-name CacheHitCount \
  --dimensions Name=ApiName,Value=CognitoAuthProxy \
  --start-time $(date -u -v-1H +%Y-%m-%dT%H:%M:%S)Z \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S)Z \
  --period 300 \
  --statistics Sum \
  --profile YOUR_AWS_PROFILE
```

## Troubleshooting

### Direct Cognito Access Not Blocked by WAF

- Wait 5-10 minutes for WAF association to propagate
- Verify WAF is associated with the Cognito User Pool:
  ```bash
  aws wafv2 list-resources-for-web-acl \
    --web-acl-arn WAF_ARN \
    --resource-type COGNITO_USER_POOL \
    --profile YOUR_AWS_PROFILE
  ```

### Cache Not Working

- Verify the cache cluster status is `AVAILABLE` (takes ~5-10 minutes after deployment)
- Ensure the Authorization header and scope are consistent between requests
- Check cache TTL hasn't expired
- Review CloudWatch metrics for cache hit/miss counts

### Invalid Credentials

- Verify the client ID and client secret are correct
- Ensure the app client has `client_credentials` grant enabled
- Check that the requested scope is allowed for the app client

### Method 3: invalid_scope Error

- Ensure the scope value is URL-encoded in the query string
- For example, `https://my-api/read` must be sent as `scope=https%3A%2F%2Fmy-api%2Fread`
