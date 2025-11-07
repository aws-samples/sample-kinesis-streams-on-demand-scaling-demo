import * as cdk from 'aws-cdk-lib';
import { Template, Match } from 'aws-cdk-lib/assertions';
import { KinesisOnDemandDemoStack } from '../src/kinesis-ondemand-demo-stack';

describe('KinesisOnDemandDemoStack', () => {
  let app: cdk.App;
  let stack: KinesisOnDemandDemoStack;
  let template: Template;

  beforeEach(() => {
    app = new cdk.App();
    stack = new KinesisOnDemandDemoStack(app, 'TestStack', {
      environment: 'test',
      env: {
        account: '123456789012',
        region: 'us-east-1',
      },
    });
    template = Template.fromStack(stack);
  });

  describe('VPC Resources', () => {
    test('creates VPC with correct configuration', () => {
      template.hasResourceProperties('AWS::EC2::VPC', {
        CidrBlock: '10.0.0.0/16',
        EnableDnsHostnames: true,
        EnableDnsSupport: true,
      });
    });

    test('creates public and private subnets', () => {
      template.resourceCountIs('AWS::EC2::Subnet', 4); // 2 AZs × 2 subnet types
      
      // Check for public subnets
      template.hasResourceProperties('AWS::EC2::Subnet', {
        MapPublicIpOnLaunch: true,
      });

      // Check for private subnets
      template.hasResourceProperties('AWS::EC2::Subnet', {
        MapPublicIpOnLaunch: false,
      });
    });

    test('creates NAT gateway for private subnet connectivity', () => {
      template.resourceCountIs('AWS::EC2::NatGateway', 1);
    });
  });

  describe('Kinesis Stream', () => {
    test('creates Kinesis stream with On-Demand mode', () => {
      template.hasResourceProperties('AWS::Kinesis::Stream', {
        Name: 'social-media-stream-test',
        StreamModeDetails: {
          StreamMode: 'ON_DEMAND',
        },
        RetentionPeriod: 24,
        StreamEncryption: {
          EncryptionType: 'KMS',
          KeyId: 'alias/aws/kinesis',
        },
      });
    });
  });

  describe('ECS Resources', () => {
    test('creates ECS cluster with container insights', () => {
      template.hasResourceProperties('AWS::ECS::Cluster', {
        ClusterName: 'kinesis-demo-test',
        ClusterSettings: [
          {
            Name: 'containerInsights',
            Value: 'enabled',
          },
        ],
      });
    });

    test('creates task definition with correct configuration', () => {
      template.hasResourceProperties('AWS::ECS::TaskDefinition', {
        Family: 'kinesis-ondemand-demo-test',
        NetworkMode: 'awsvpc',
        RequiresCompatibilities: ['FARGATE'],
        Cpu: '1024',
        Memory: '2048',
      });
    });

    test('creates ECS service with correct configuration', () => {
      template.hasResourceProperties('AWS::ECS::Service', {
        ServiceName: 'kinesis-ondemand-demo-test',
        DesiredCount: 1,
        LaunchType: 'FARGATE',
        EnableExecuteCommand: true,
        DeploymentConfiguration: {
          MaximumPercent: 200,
          MinimumHealthyPercent: 50,
          DeploymentCircuitBreaker: {
            Enable: true,
            Rollback: true,
          },
        },
      });
    });

    test('creates auto scaling target and policies', () => {
      template.hasResourceProperties('AWS::ApplicationAutoScaling::ScalableTarget', {
        MaxCapacity: 50,
        MinCapacity: 1,
        ResourceId: Match.stringLikeRegexp('service/.*/.*'),
        ScalableDimension: 'ecs:service:DesiredCount',
        ServiceNamespace: 'ecs',
      });

      template.hasResourceProperties('AWS::ApplicationAutoScaling::ScalingPolicy', {
        PolicyType: 'TargetTrackingScaling',
        TargetTrackingScalingPolicyConfiguration: {
          TargetValue: 70,
          PredefinedMetricSpecification: {
            PredefinedMetricType: 'ECSServiceAverageCPUUtilization',
          },
        },
      });
    });
  });

  describe('IAM Roles and Policies', () => {
    test('creates ECS task execution role with correct policies', () => {
      template.hasResourceProperties('AWS::IAM::Role', {
        RoleName: 'KinesisDemo-ECSTaskExecutionRole-test',
        AssumeRolePolicyDocument: {
          Statement: [
            {
              Effect: 'Allow',
              Principal: {
                Service: 'ecs-tasks.amazonaws.com',
              },
              Action: 'sts:AssumeRole',
            },
          ],
        },
        ManagedPolicyArns: [
          'arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy',
        ],
      });
    });

    test('creates ECS task role with Kinesis permissions', () => {
      template.hasResourceProperties('AWS::IAM::Role', {
        RoleName: 'KinesisDemo-ECSTaskRole-test',
        AssumeRolePolicyDocument: {
          Statement: [
            {
              Effect: 'Allow',
              Principal: {
                Service: 'ecs-tasks.amazonaws.com',
              },
              Action: 'sts:AssumeRole',
            },
          ],
        },
      });

      // Check for Kinesis permissions in inline policy
      template.hasResourceProperties('AWS::IAM::Policy', {
        PolicyDocument: {
          Statement: Match.arrayWith([
            {
              Effect: 'Allow',
              Action: [
                'kinesis:PutRecord',
                'kinesis:PutRecords',
                'kinesis:DescribeStream',
                'kinesis:ListStreams',
              ],
              Resource: Match.anyValue(),
            },
          ]),
        },
      });
    });

    test('creates Step Functions controller role with ECS permissions', () => {
      template.hasResourceProperties('AWS::IAM::Role', {
        RoleName: 'KinesisDemo-StepFunctionsControllerRole-test',
        AssumeRolePolicyDocument: {
          Statement: [
            {
              Effect: 'Allow',
              Principal: {
                Service: 'lambda.amazonaws.com',
              },
              Action: 'sts:AssumeRole',
            },
          ],
        },
      });

      // Check for ECS permissions
      template.hasResourceProperties('AWS::IAM::Policy', {
        PolicyDocument: {
          Statement: Match.arrayWith([
            {
              Effect: 'Allow',
              Action: [
                'ecs:UpdateService',
                'ecs:DescribeServices',
                'ecs:DescribeClusters',
                'ecs:DescribeTasks',
                'ecs:ListTasks',
                'ecs:RegisterTaskDefinition',
                'ecs:DescribeTaskDefinition',
              ],
              Resource: Match.anyValue(),
            },
          ]),
        },
      });
    });
  });

  describe('Lambda Functions', () => {
    test('creates message processor Lambda function', () => {
      template.hasResourceProperties('AWS::Lambda::Function', {
        FunctionName: 'kinesis-demo-message-processor-test',
        Runtime: 'python3.11',
        Handler: 'message_processor.lambda_handler',
        Timeout: 300,
        MemorySize: 256,
      });
    });

    test('creates cost calculator Lambda function', () => {
      template.hasResourceProperties('AWS::Lambda::Function', {
        FunctionName: 'kinesis-demo-cost-calculator-test',
        Runtime: 'python3.11',
        Handler: 'cost_calculator.lambda_handler',
        Timeout: 120,
        MemorySize: 256,
      });
    });

    test('creates Step Functions controller Lambda function', () => {
      template.hasResourceProperties('AWS::Lambda::Function', {
        FunctionName: 'kinesis-demo-stepfunctions-controller-test',
        Runtime: 'python3.11',
        Handler: 'step_functions_controller.lambda_handler',
        Timeout: 120,
        MemorySize: 256,
        Environment: {
          Variables: {
            CLUSTER_NAME: 'kinesis-demo-test',
            SERVICE_NAME: 'kinesis-ondemand-demo-test',
            ENVIRONMENT: 'test',
          },
        },
      });
    });

    test('creates Kinesis event source mapping for message processor', () => {
      template.hasResourceProperties('AWS::Lambda::EventSourceMapping', {
        BatchSize: 100,
        StartingPosition: 'LATEST',
        MaximumBatchingWindowInSeconds: 5,
      });
    });
  });

  describe('Step Functions', () => {
    test('creates Step Functions state machine', () => {
      template.hasResourceProperties('AWS::StepFunctions::StateMachine', {
        StateMachineName: 'kinesis-demo-test',
        StateMachineType: 'STANDARD',
      });
    });

    test('creates Step Functions execution role', () => {
      template.hasResourceProperties('AWS::IAM::Role', {
        RoleName: 'KinesisDemo-StepFunctionsRole-test',
        AssumeRolePolicyDocument: {
          Statement: [
            {
              Effect: 'Allow',
              Principal: {
                Service: 'states.amazonaws.com',
              },
              Action: 'sts:AssumeRole',
            },
          ],
        },
      });
    });
  });

  describe('API Gateway', () => {
    test('creates REST API with correct configuration', () => {
      template.hasResourceProperties('AWS::ApiGateway::RestApi', {
        Name: 'kinesis-demo-stepfunctions-api-test',
        Description: 'API for controlling Kinesis On-Demand Demo via Step Functions',
        EndpointConfiguration: {
          Types: ['REGIONAL'],
        },
      });
    });

    test('creates demo resource with POST and GET methods', () => {
      template.hasResourceProperties('AWS::ApiGateway::Resource', {
        PathPart: 'demo',
      });

      // Check for POST method
      template.hasResourceProperties('AWS::ApiGateway::Method', {
        HttpMethod: 'POST',
        Integration: {
          Type: 'AWS',
          IntegrationHttpMethod: 'POST',
          Uri: Match.stringLikeRegexp('arn:aws:apigateway:.*:states:action/StartExecution'),
        },
      });

      // Check for GET method
      template.hasResourceProperties('AWS::ApiGateway::Method', {
        HttpMethod: 'GET',
        Integration: {
          Type: 'AWS',
          IntegrationHttpMethod: 'POST',
          Uri: Match.stringLikeRegexp('arn:aws:apigateway:.*:states:action/DescribeExecution'),
        },
      });
    });

    test('creates API Gateway deployment', () => {
      template.hasResourceProperties('AWS::ApiGateway::Deployment', {
        StageName: Match.anyValue(),
      });
    });
  });

  describe('CloudWatch Resources', () => {
    test('creates CloudWatch dashboard', () => {
      template.hasResourceProperties('AWS::CloudWatch::Dashboard', {
        DashboardName: 'kinesis-ondemand-demo-test',
      });
    });

    test('creates log groups with correct retention', () => {
      // ECS log group
      template.hasResourceProperties('AWS::Logs::LogGroup', {
        LogGroupName: '/ecs/kinesis-ondemand-demo',
        RetentionInDays: 7,
      });

      // Lambda log groups
      template.hasResourceProperties('AWS::Logs::LogGroup', {
        LogGroupName: '/aws/lambda/kinesis-demo-message-processor-test',
        RetentionInDays: 7,
      });

      template.hasResourceProperties('AWS::Logs::LogGroup', {
        LogGroupName: '/aws/lambda/kinesis-demo-cost-calculator-test',
        RetentionInDays: 7,
      });

      template.hasResourceProperties('AWS::Logs::LogGroup', {
        LogGroupName: '/aws/lambda/kinesis-demo-stepfunctions-controller-test',
        RetentionInDays: 7,
      });

      template.hasResourceProperties('AWS::Logs::LogGroup', {
        LogGroupName: '/aws/stepfunctions/kinesis-demo-test',
        RetentionInDays: 7,
      });
    });
  });

  describe('Stack Outputs', () => {
    test('creates all required outputs', () => {
      const outputs = template.findOutputs('*');
      
      expect(outputs).toHaveProperty('KinesisStreamName');
      expect(outputs).toHaveProperty('EcsClusterName');
      expect(outputs).toHaveProperty('EcsServiceName');
      expect(outputs).toHaveProperty('StateMachineArn');
      expect(outputs).toHaveProperty('ApiEndpoint');
      expect(outputs).toHaveProperty('DashboardUrl');
      expect(outputs).toHaveProperty('StepFunctionsConsoleUrl');
    });

    test('outputs have correct export names', () => {
      template.hasOutput('KinesisStreamName', {
        Export: {
          Name: 'TestStack-KinesisStreamName',
        },
      });

      template.hasOutput('EcsClusterName', {
        Export: {
          Name: 'TestStack-EcsClusterName',
        },
      });

      template.hasOutput('StateMachineArn', {
        Export: {
          Name: 'TestStack-StateMachineArn',
        },
      });
    });
  });

  describe('Resource Tagging', () => {
    test('applies consistent tags to resources', () => {
      // Check ECS cluster tags
      template.hasResourceProperties('AWS::ECS::Cluster', {
        Tags: Match.arrayWith([
          {
            Key: 'Project',
            Value: 'KinesisOnDemandDemo',
          },
          {
            Key: 'Environment',
            Value: 'test',
          },
          {
            Key: 'ManagedBy',
            Value: 'CDK',
          },
        ]),
      });
    });
  });

  describe('Security Configuration', () => {
    test('uses least privilege IAM policies', () => {
      // Check that Kinesis permissions are scoped to specific stream
      template.hasResourceProperties('AWS::IAM::Policy', {
        PolicyDocument: {
          Statement: Match.arrayWith([
            {
              Effect: 'Allow',
              Action: [
                'kinesis:PutRecord',
                'kinesis:PutRecords',
                'kinesis:DescribeStream',
                'kinesis:ListStreams',
              ],
              Resource: Match.stringLikeRegexp('arn:aws:kinesis:.*:.*:stream/social-media-stream-test'),
            },
          ]),
        },
      });
    });

    test('uses encryption for Kinesis stream', () => {
      template.hasResourceProperties('AWS::Kinesis::Stream', {
        StreamEncryption: {
          EncryptionType: 'KMS',
          KeyId: 'alias/aws/kinesis',
        },
      });
    });

    test('CloudWatch metrics permissions are properly scoped', () => {
      template.hasResourceProperties('AWS::IAM::Policy', {
        PolicyDocument: {
          Statement: Match.arrayWith([
            {
              Effect: 'Allow',
              Action: 'cloudwatch:PutMetricData',
              Resource: '*',
              Condition: {
                StringEquals: {
                  'cloudwatch:namespace': Match.arrayWith([
                    'KinesisOnDemandDemo/test',
                    'KinesisOnDemandDemo',
                  ]),
                },
              },
            },
          ]),
        },
      });
    });
  });

  describe('Resource Limits and Configuration', () => {
    test('configures appropriate resource limits', () => {
      // ECS task definition limits
      template.hasResourceProperties('AWS::ECS::TaskDefinition', {
        Cpu: '1024',
        Memory: '2048',
      });

      // Lambda function limits
      template.hasResourceProperties('AWS::Lambda::Function', {
        Timeout: 300, // Message processor
        MemorySize: 256,
      });

      template.hasResourceProperties('AWS::Lambda::Function', {
        Timeout: 120, // Cost calculator and Step Functions controller
        MemorySize: 256,
      });

      // Auto scaling limits
      template.hasResourceProperties('AWS::ApplicationAutoScaling::ScalableTarget', {
        MaxCapacity: 50,
        MinCapacity: 1,
      });
    });

    test('configures health checks and monitoring', () => {
      // ECS service health check
      template.hasResourceProperties('AWS::ECS::TaskDefinition', {
        ContainerDefinitions: Match.arrayWith([
          {
            HealthCheck: {
              Command: ['CMD-SHELL', 'python health_check.py || exit 1'],
              Interval: 30,
              Timeout: 10,
              Retries: 3,
              StartPeriod: 60,
            },
          },
        ]),
      });

      // ECS service deployment configuration
      template.hasResourceProperties('AWS::ECS::Service', {
        DeploymentConfiguration: {
          MaximumPercent: 200,
          MinimumHealthyPercent: 50,
          DeploymentCircuitBreaker: {
            Enable: true,
            Rollback: true,
          },
        },
      });
    });
  });

  describe('Environment-specific Configuration', () => {
    test('uses environment-specific naming', () => {
      template.hasResourceProperties('AWS::Kinesis::Stream', {
        Name: 'social-media-stream-test',
      });

      template.hasResourceProperties('AWS::ECS::Cluster', {
        ClusterName: 'kinesis-demo-test',
      });

      template.hasResourceProperties('AWS::ECS::Service', {
        ServiceName: 'kinesis-ondemand-demo-test',
      });
    });

    test('configures environment variables correctly', () => {
      template.hasResourceProperties('AWS::ECS::TaskDefinition', {
        ContainerDefinitions: Match.arrayWith([
          {
            Environment: Match.arrayWith([
              {
                Name: 'ENVIRONMENT',
                Value: 'test',
              },
              {
                Name: 'CLOUDWATCH_NAMESPACE',
                Value: 'KinesisOnDemandDemo/test',
              },
              {
                Name: 'CONTROLLER_MODE',
                Value: 'step_functions',
              },
            ]),
          },
        ]),
      });
    });
  });
});