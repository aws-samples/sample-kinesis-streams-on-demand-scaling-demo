import { NagSuppressions } from 'cdk-nag';
import { Stack } from 'aws-cdk-lib';

export function addSecuritySuppressions(stack: Stack) {
  // Get the account and region from the stack context
  const account = stack.account;
  const region = stack.region;
  // Suppress acceptable AWS managed policy usage for basic Lambda execution
  NagSuppressions.addStackSuppressions(stack, [
    {
      id: 'AwsSolutions-IAM4',
      reason: 'AWS managed policy AWSLambdaBasicExecutionRole is acceptable for basic Lambda logging',
      appliesTo: ['Policy::arn:<AWS::Partition>:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole']
    },
    {
      id: 'AwsSolutions-IAM4',
      reason: 'AWS managed policy AmazonECSTaskExecutionRolePolicy is acceptable for ECS task execution',
      appliesTo: ['Policy::arn:<AWS::Partition>:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy']
    }
  ]);

  // Comprehensive IAM wildcard suppressions - using dynamic account and region
  NagSuppressions.addStackSuppressions(stack, [
    {
      id: 'AwsSolutions-IAM5',
      reason: 'Comprehensive suppression for acceptable wildcard permissions in this demo: ECR GetAuthorizationToken (AWS requirement), CloudWatch PutMetricData (restricted by namespace), X-Ray tracing, CloudWatch Logs, ECS task management, Lambda function qualifiers, Bedrock inference profiles (cross-region routing to us-east-1, us-west-2, us-east-2), and Sentiment Consumer log streams. All wildcards are either AWS service requirements or appropriately scoped for demo functionality.',
      appliesTo: [
        'Resource::*',
        `Resource::arn:aws:ecr:${region}:${account}:repository/kinesis-ondemand-demo*`,
        `Resource::arn:aws:ecr:${region}:${account}:repository/cdk-*`,
        `Resource::arn:aws:logs:${region}:${account}:log-group:/ecs/kinesis-ondemand-demo*`,
        `Resource::arn:aws:logs:${region}:${account}:log-group:/aws/lambda/sentiment-analysis-consumer-production:*`,
        `Resource::arn:aws:logs:${region}:${account}:log-group:/aws/lambda/sentiment-analysis-consumer-production/insights:*`,
        `Resource::arn:aws:ecs:${region}:${account}:task-definition/*`,
        `Resource::arn:aws:ecs:${region}:${account}:task/<DemoCluster8CB095E3>/*`,
        'Resource::arn:aws:bedrock:us-east-1:*:inference-profile/*',
        'Resource::arn:aws:bedrock:us-west-2:*:inference-profile/*',
        'Resource::arn:aws:bedrock:us-east-2:*:inference-profile/*',
        'Resource::<StepFunctionsController286FB483.Arn>:*'
      ]
    }
  ]);

  // Suppress ECS environment variables warning (acceptable for demo)
  NagSuppressions.addStackSuppressions(stack, [
    {
      id: 'AwsSolutions-ECS2',
      reason: 'Environment variables contain non-sensitive configuration data for demo purposes. Moving to Parameter Store would add unnecessary complexity for this demo.'
    }
  ]);

  // Suppress Lambda runtime warning (Python 3.11 is current and secure)
  NagSuppressions.addStackSuppressions(stack, [
    {
      id: 'AwsSolutions-L1',
      reason: 'Python 3.11 is a current, supported, and secure runtime. CDK version 2.196.0 may not yet support Python 3.12. Python 3.11 receives security updates and is appropriate for this demo.'
    }
  ]);
}