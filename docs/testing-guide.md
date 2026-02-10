# Testing Guide

This guide provides comprehensive test commands to validate your Cognito OAuth2 Token Proxy deployment.

## Prerequisites

Before testing, ensure you have:
- Deployed the solution successfully
- Retrieved the API endpoint URL from stack outputs
- Retrieved the API key value from AWS API Gateway console or stack outputs
- Your Cognito client credentials (client ID and client secret)

## Test Scenarios

### Test 1: API Gateway with Correct API Key

This test validates that the API Gateway endpoint works correctly with a valid API key.

**Expected Result**: ✓ Success - Returns OAuth2 access token

```bash
curl -X POST https://API_ID.execute-api.REGION.amazonaws.com/STAGE/oauth2/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -H "x-api-key: YOUR_API_KEY" \
  -d "grant_type=client_credentials&client_id=CLIENT_ID&client_secret=CLIENT_SECRET"
```

**Expected Response**:
```json
{
  "access_token": "eyJraWQiOiJ...",
  "expires_in": 3600,
  "token_type": "Bearer"
}
```

### Test 2: API Gateway without API Key

This test validates that API Gateway blocks requests without an API key.

**Expected Result**: ✗ Failure - 403 Forbidden

```bash
curl -X POST https://API_ID.execute-api.REGION.amazonaws.com/STAGE/oauth2/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=client_credentials&client_id=CLIENT_ID&client_secret=CLIENT_SECRET"
```

**Expected Response**:
```json
{
  "message": "Forbidden"
}
```

### Test 3: API Gateway with Invalid API Key

This test validates that API Gateway blocks requests with an incorrect API key.

**Expected Result**: ✗ Failure - 403 Forbidden

```bash
curl -X POST https://API_ID.execute-api.REGION.amazonaws.com/STAGE/oauth2/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -H "x-api-key: invalid-key-value" \
  -d "grant_type=client_credentials&client_id=CLIENT_ID&client_secret=CLIENT_SECRET"
```

**Expected Response**:
```json
{
  "message": "Forbidden"
}
```

### Test 4: Direct Cognito Access without API Key

This test validates that WAF blocks direct access to Cognito without the API key.

**Expected Result**: ✗ Failure - 403 Forbidden (after WAF propagation)

```bash
curl -X POST https://YOUR_COGNITO_DOMAIN.auth.REGION.amazoncognito.com/oauth2/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -H "Authorization: Basic $(echo -n 'CLIENT_ID:CLIENT_SECRET' | base64)" \
  -d "grant_type=client_credentials"
```

**Expected Response**:
```json
{
  "message": "WAF is preventing direct access to Cognito. Please use the API Gateway endpoint with a valid API key."
}
```

**Note**: WAF associations may take 5-10 minutes to propagate after deployment. If this test initially succeeds, wait a few minutes and try again.

### Test 5: Direct Cognito Access with API Key

This test validates that WAF allows direct Cognito access when the correct API key is provided.

**Expected Result**: ✓ Success - Returns OAuth2 access token

```bash
curl -X POST https://YOUR_COGNITO_DOMAIN.auth.REGION.amazoncognito.com/oauth2/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -H "x-api-key: YOUR_API_KEY" \
  -H "Authorization: Basic $(echo -n 'CLIENT_ID:CLIENT_SECRET' | base64)" \
  -d "grant_type=client_credentials"
```

**Expected Response**:
```json
{
  "access_token": "eyJraWQiOiJ...",
  "expires_in": 3600,
  "token_type": "Bearer"
}
```

## Test Summary

| Test | Endpoint | API Key | Expected Result |
|------|----------|---------|-----------------|
| 1 | API Gateway | Valid | ✓ Success - Returns token |
| 2 | API Gateway | None | ✗ 403 Forbidden |
| 3 | API Gateway | Invalid | ✗ 403 Forbidden |
| 4 | Direct Cognito | None | ✗ 403 Forbidden (WAF blocks) |
| 5 | Direct Cognito | Valid | ✓ Success - Returns token |

## Cache Testing

To test cache behavior:

1. Run Test 1 and note the response time
2. Run Test 1 again immediately with the same credentials
3. The second request should be faster (cache hit)

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

### API Gateway Returns 403 Forbidden

- Verify the API key is correct
- Check that the API key is associated with the usage plan
- Ensure the `x-api-key` header is included in the request

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

- Verify the Authorization header is consistent between requests
- Check cache TTL hasn't expired
- Review CloudWatch metrics for cache hit/miss counts

## Additional Testing

For production deployments, consider testing:

- Token expiration and refresh behavior
- Concurrent request handling
- Cache invalidation scenarios
- Different OAuth2 scopes
- Error handling for invalid credentials
