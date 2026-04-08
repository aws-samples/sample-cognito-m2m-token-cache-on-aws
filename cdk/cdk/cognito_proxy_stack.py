from aws_cdk import (
    Stack,
    CfnOutput,
    Duration,
    RemovalPolicy,
    aws_apigateway as apigw,
    aws_wafv2 as wafv2,
    aws_logs as logs,
    aws_secretsmanager as secretsmanager,
)
from constructs import Construct


class CognitoProxyStack(Stack):
    """
    CDK Stack for Cognito OAuth2 Token Proxy with API Gateway Caching.
    
    This stack creates an API Gateway proxy in front of AWS Cognito's OAuth2 token endpoint,
    adding intelligent caching. WAF protection uses a custom origin-verify header to ensure
    only requests from API Gateway can reach Cognito directly.
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        cognito_domain: str,
        cognito_user_pool_arn: str,
        stage_name: str = "dev",
        cache_ttl_seconds: int = 3600,
        cache_size_gb: str = "0.5",
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Validate cache size
        valid_cache_sizes = ["0.5", "1.6", "6.1", "13.5", "28.4", "58.2", "118", "237"]
        if cache_size_gb not in valid_cache_sizes:
            raise ValueError(f"cache_size_gb must be one of {valid_cache_sizes}")

        if not cognito_user_pool_arn:
            raise ValueError("cognito_user_pool_arn is required for WAF protection")

        # Create CloudWatch Log Group for API Gateway access logs
        access_log_group = logs.LogGroup(
            self,
            "ApiGatewayAccessLogs",
            log_group_name=f"/aws/apigateway/{construct_id}-access-logs",
            retention=logs.RetentionDays.ONE_MONTH,
            removal_policy=RemovalPolicy.DESTROY,
        )

        # Create API Gateway REST API
        api = apigw.RestApi(
            self,
            "CognitoProxy",
            rest_api_name="CognitoAuthProxy",
            description="Proxy to Cognito OAuth2 token endpoint with caching",
            endpoint_types=[apigw.EndpointType.REGIONAL],
            deploy=False,  # We'll create a custom deployment
        )

        # Create origin verify secret for WAF validation
        origin_verify_secret = secretsmanager.Secret(
            self,
            "OriginVerifySecret",
            description="Secret used by API Gateway to prove origin to WAF on Cognito",
            generate_secret_string=secretsmanager.SecretStringGenerator(
                secret_string_template="{}",
                generate_string_key="origin-verify-token",
                password_length=64,
                exclude_punctuation=True,
            ),
        )

        # Resolve the secret value for use in integration parameters and WAF
        origin_verify_value = origin_verify_secret.secret_value_from_json("origin-verify-token")

        # Create /oauth2/token resource path
        oauth2_resource = api.root.add_resource("oauth2")
        token_resource = oauth2_resource.add_resource("token")

        # VTL request template for transforming requests
        request_template = """#if($input.params().header.containsKey("Authorization"))
#set($context.requestOverride.header.Authorization = $input.params().header.get("Authorization"))
#set($body = $input.body)
#set($pairs = $body.split("&"))
#set($hasScope = false)
#set($scopeValue = "")
#foreach($pair in $pairs)
#set($kv = $pair.split("="))
#if($kv[0] == "scope")
#set($hasScope = true)
#if($kv.size() > 1)
#set($scopeValue = $kv[1])
#end
#end
#end
#if($hasScope)
grant_type=client_credentials&scope=$scopeValue
#else
grant_type=client_credentials&scope=
#end
#elseif($input.params().querystring.containsKey("client_id") && $input.params().querystring.containsKey("client_secret"))
#set($clientId = $input.params().querystring.get("client_id"))
#set($clientSecret = $input.params().querystring.get("client_secret"))
#set($credentials = "$clientId:$clientSecret")
#set($encodedCreds = $util.base64Encode($credentials))
#set($context.requestOverride.header.Authorization = "Basic $encodedCreds")
#if($input.params().querystring.containsKey("scope"))
grant_type=client_credentials&scope=$input.params().querystring.get("scope")
#else
grant_type=client_credentials&scope=
#end
#else
#set($body = $input.body)
#set($pairs = $body.split("&"))
#set($clientId = "")
#set($clientSecret = "")
#set($hasScope = false)
#set($scopeValue = "")
#foreach($pair in $pairs)
#set($kv = $pair.split("="))
#if($kv[0] == "client_id")
#set($clientId = $kv[1])
#end
#if($kv[0] == "client_secret")
#set($clientSecret = $kv[1])
#end
#if($kv[0] == "scope")
#set($hasScope = true)
#if($kv.size() > 1)
#set($scopeValue = $kv[1])
#end
#end
#end
#if($clientId && $clientSecret)
#set($credentials = "$clientId:$clientSecret")
#set($encodedCreds = $util.base64Encode($credentials))
#set($context.requestOverride.header.Authorization = "Basic $encodedCreds")
#end
#if($hasScope)
grant_type=client_credentials&scope=$scopeValue
#else
grant_type=client_credentials&scope=
#end
#end
#set($context.requestOverride.header.Accept = "application/json")"""

        # Create HTTP integration to Cognito
        integration = apigw.HttpIntegration(
            f"https://{cognito_domain}/oauth2/token",
            http_method="POST",
            options=apigw.IntegrationOptions(
                passthrough_behavior=apigw.PassthroughBehavior.WHEN_NO_TEMPLATES,
                cache_namespace=token_resource.node.id,
                cache_key_parameters=[
                    "integration.request.header.Authorization",
                    "integration.request.querystring.scope",
                ],
                request_parameters={
                    "integration.request.header.Authorization": "method.request.header.Authorization",
                    "integration.request.header.x-origin-verify": "stageVariables.originVerifyToken",
                    "integration.request.querystring.scope": "method.request.querystring.scope",
                },
                request_templates={
                    "application/x-www-form-urlencoded": request_template
                },
                integration_responses=[
                    apigw.IntegrationResponse(
                        status_code="200",
                    )
                ],
            ),
        )

        # Add POST method to /oauth2/token
        token_resource.add_method(
            "POST",
            integration,
            api_key_required=False,
            request_parameters={
                "method.request.header.Authorization": False,
                "method.request.header.Accept": False,
                "method.request.querystring.scope": False,
            },
            method_responses=[
                apigw.MethodResponse(
                    status_code="200",
                    response_models={
                        "application/json": apigw.Model.EMPTY_MODEL,
                    },
                )
            ],
        )

        # Create deployment
        deployment = apigw.Deployment(
            self,
            "ApiGatewayDeployment",
            api=api,
            description="Deployment for Cognito OAuth2 Token Proxy",
        )

        # Create stage with caching and logging
        stage = apigw.Stage(
            self,
            "ApiGatewayStage",
            deployment=deployment,
            stage_name=stage_name,
            cache_cluster_enabled=True,
            cache_cluster_size=cache_size_gb,
            access_log_destination=apigw.LogGroupLogDestination(access_log_group),
            access_log_format=apigw.AccessLogFormat.json_with_standard_fields(
                caller=True,
                http_method=True,
                ip=True,
                protocol=True,
                request_time=True,
                resource_path=True,
                response_length=True,
                status=True,
                user=True,
            ),
            logging_level=apigw.MethodLoggingLevel.INFO,
            data_trace_enabled=True,
            metrics_enabled=True,
            method_options={
                "/*/*": apigw.MethodDeploymentOptions(
                    caching_enabled=False,
                    logging_level=apigw.MethodLoggingLevel.INFO,
                    data_trace_enabled=True,
                    metrics_enabled=True,
                ),
                "/oauth2/token/POST": apigw.MethodDeploymentOptions(
                    caching_enabled=True,
                    cache_ttl=Duration.seconds(cache_ttl_seconds),
                    cache_data_encrypted=True,
                    logging_level=apigw.MethodLoggingLevel.INFO,
                    data_trace_enabled=True,
                    metrics_enabled=True,
                ),
            },
        )

        # Inject origin-verify token as a stage variable so the integration can reference it
        cfn_stage = stage.node.default_child
        cfn_stage.variables = {
            "originVerifyToken": origin_verify_value.unsafe_unwrap()
        }

        # Create WAF WebACL to protect Cognito User Pool
        web_acl = wafv2.CfnWebACL(
            self,
            "CognitoProtectionWebACL",
            scope="REGIONAL",
            default_action=wafv2.CfnWebACL.DefaultActionProperty(
                block=wafv2.CfnWebACL.BlockActionProperty(
                    custom_response=wafv2.CfnWebACL.CustomResponseProperty(
                        response_code=403,
                        custom_response_body_key="CognitoDenied"
                    )
                )
            ),
            visibility_config=wafv2.CfnWebACL.VisibilityConfigProperty(
                cloud_watch_metrics_enabled=True,
                metric_name="CognitoProtectionWebACL",
                sampled_requests_enabled=True
            ),
            rules=[
                wafv2.CfnWebACL.RuleProperty(
                    name="allow-origin-verify-requests",
                    priority=0,
                    statement=wafv2.CfnWebACL.StatementProperty(
                        byte_match_statement=wafv2.CfnWebACL.ByteMatchStatementProperty(
                            search_string=origin_verify_value.unsafe_unwrap(),
                            field_to_match=wafv2.CfnWebACL.FieldToMatchProperty(
                                single_header={"Name": "x-origin-verify"}
                            ),
                            text_transformations=[
                                wafv2.CfnWebACL.TextTransformationProperty(
                                    priority=0,
                                    type="NONE"
                                )
                            ],
                            positional_constraint="EXACTLY"
                        )
                    ),
                    action=wafv2.CfnWebACL.RuleActionProperty(
                        allow={}
                    ),
                    visibility_config=wafv2.CfnWebACL.VisibilityConfigProperty(
                        cloud_watch_metrics_enabled=True,
                        metric_name="allow-origin-verify-requests",
                        sampled_requests_enabled=True
                    )
                )
            ],
            custom_response_bodies={
                "CognitoDenied": wafv2.CfnWebACL.CustomResponseBodyProperty(
                    content_type="APPLICATION_JSON",
                    content='{"message":"WAF is preventing direct access to Cognito. Please use the API Gateway endpoint."}'
                )
            }
        )

        # Associate WAF with Cognito User Pool
        wafv2.CfnWebACLAssociation(
            self,
            "CognitoWAFAssociation",
            resource_arn=cognito_user_pool_arn,
            web_acl_arn=web_acl.attr_arn
        )

        CfnOutput(
            self,
            "WebACLOutput",
            description="WAF WebACL protecting Cognito User Pool",
            value=web_acl.attr_arn,
        )

        # Outputs
        CfnOutput(
            self,
            "ApiEndpointOutput",
            description="API Gateway endpoint URL for the OAuth2 token proxy",
            value=f"https://{api.rest_api_id}.execute-api.{self.region}.amazonaws.com/{stage_name}/oauth2/token",
        )

        CfnOutput(
            self,
            "OriginVerifySecretOutput",
            description="Secrets Manager ARN for the origin verify secret (used internally by WAF)",
            value=origin_verify_secret.secret_arn,
        )

        CfnOutput(
            self,
            "CacheClusterSizeOutput",
            description="Cache cluster size",
            value=cache_size_gb,
        )

        CfnOutput(
            self,
            "CacheTtlOutput",
            description="Cache TTL in seconds",
            value=str(cache_ttl_seconds),
        )
