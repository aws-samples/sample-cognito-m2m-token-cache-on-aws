#!/usr/bin/env python3
import os
import aws_cdk as cdk
from cdk.cognito_proxy_stack import CognitoProxyStack
from cdk_nag import AwsSolutionsChecks, NagSuppressions


app = cdk.App()

# Get configuration from context or environment variables
cognito_domain = app.node.try_get_context("cognito_domain")
cognito_user_pool_arn = app.node.try_get_context("cognito_user_pool_arn")
stage_name = app.node.try_get_context("stage_name") or "dev"
cache_ttl_seconds = int(app.node.try_get_context("cache_ttl_seconds") or 3600)
cache_size_gb = app.node.try_get_context("cache_size_gb") or "0.5"
enable_waf_protection = app.node.try_get_context("enable_waf_protection")
if enable_waf_protection is None:
    enable_waf_protection = True
else:
    enable_waf_protection = enable_waf_protection.lower() in ['true', '1', 'yes']

# Validate required parameters
if not cognito_domain:
    raise ValueError(
        "cognito_domain is required. "
        "Provide it via context: cdk deploy -c cognito_domain=your-domain.auth.region.amazoncognito.com"
    )

if enable_waf_protection and not cognito_user_pool_arn:
    raise ValueError(
        "cognito_user_pool_arn is required when WAF protection is enabled. "
        "Provide it via context: cdk deploy -c cognito_user_pool_arn=arn:aws:cognito-idp:region:account:userpool/pool-id "
        "or disable WAF: -c enable_waf_protection=false"
    )

CognitoProxyStack(
    app,
    "CognitoProxyStack",
    cognito_domain=cognito_domain,
    cognito_user_pool_arn=cognito_user_pool_arn,
    stage_name=stage_name,
    cache_ttl_seconds=cache_ttl_seconds,
    cache_size_gb=cache_size_gb,
    enable_waf_protection=enable_waf_protection,
    env=cdk.Environment(
        account=os.getenv("CDK_DEFAULT_ACCOUNT"),
        region=os.getenv("CDK_DEFAULT_REGION"),
    ),
    description="Cognito OAuth2 Token Proxy with API Gateway Caching and WAF Protection",
)

# Add cdk-nag checks
cdk.Aspects.of(app).add(AwsSolutionsChecks(verbose=True))

# Suppress expected cdk-nag findings
stack = app.node.find_child("CognitoProxyStack")
NagSuppressions.add_stack_suppressions(stack, [
    {
        "id": "AwsSolutions-APIG2",
        "reason": "Request validation is not needed — the proxy forwards requests to Cognito which performs its own validation.",
    },
    {
        "id": "AwsSolutions-APIG4",
        "reason": "No authorization is needed on the proxy — Cognito handles authentication via client credentials.",
    },
    {
        "id": "AwsSolutions-COG4",
        "reason": "Cognito authorizer is not applicable — this is a proxy TO Cognito, not protected BY Cognito.",
    },
    {
        "id": "AwsSolutions-SMG4",
        "reason": "The origin-verify secret does not require rotation — it is an internal shared secret between API Gateway and WAF.",
    },
    {
        "id": "AwsSolutions-APIG3",
        "reason": "WAF is associated with the Cognito User Pool, not the API Gateway stage. The API Gateway is the origin, not the target.",
    },
])

app.synth()
