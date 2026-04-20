import aws_cdk as core
import aws_cdk.assertions as assertions

from cdk.cognito_proxy_stack import CognitoProxyStack


def get_stack():
    app = core.App()
    return CognitoProxyStack(
        app,
        "TestStack",
        cognito_domain="test.auth.us-east-1.amazoncognito.com",
        cognito_user_pool_arn="arn:aws:cognito-idp:us-east-1:123456789012:userpool/us-east-1_test",
        stage_name="test",
        cache_ttl_seconds=3600,
        cache_size_gb="0.5",
    )


def test_api_gateway_created():
    stack = get_stack()
    template = assertions.Template.from_stack(stack)
    template.has_resource_properties("AWS::ApiGateway::RestApi", {
        "Name": "CognitoAuthProxy",
        "EndpointConfiguration": {"Types": ["REGIONAL"]},
    })


def test_waf_web_acl_created():
    stack = get_stack()
    template = assertions.Template.from_stack(stack)
    template.has_resource_properties("AWS::WAFv2::WebACL", {
        "DefaultAction": {"Block": {}},
        "Scope": "REGIONAL",
    })


def test_waf_association_created():
    stack = get_stack()
    template = assertions.Template.from_stack(stack)
    template.has_resource_properties("AWS::WAFv2::WebACLAssociation", {
        "ResourceArn": "arn:aws:cognito-idp:us-east-1:123456789012:userpool/us-east-1_test",
    })


def test_secrets_manager_secret_created():
    stack = get_stack()
    template = assertions.Template.from_stack(stack)
    template.has_resource_properties("AWS::SecretsManager::Secret", {
        "GenerateSecretString": {
            "GenerateStringKey": "origin-verify-token",
            "PasswordLength": 64,
            "ExcludePunctuation": True,
        },
    })


def test_cache_enabled():
    stack = get_stack()
    template = assertions.Template.from_stack(stack)
    template.has_resource_properties("AWS::ApiGateway::Stage", {
        "CacheClusterEnabled": True,
        "CacheClusterSize": "0.5",
    })


def test_token_method_no_auth():
    stack = get_stack()
    template = assertions.Template.from_stack(stack)
    template.has_resource_properties("AWS::ApiGateway::Method", {
        "HttpMethod": "POST",
        "AuthorizationType": "NONE",
        "ApiKeyRequired": False,
    })
