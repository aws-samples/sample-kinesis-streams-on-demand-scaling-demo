import * as AWS from 'aws-sdk';
import { execSync } from 'child_process';
import * as path from 'path';

// Integration tests for the deployed CDK stack
// These tests validate that the infrastructure is working correctly after deployment

describe('Kinesis On-Demand Demo Integration Tests', () => {
  const environment = process.env.TEST_ENVIRONMENT || 'test';
  const region = process.env.AWS_REGION || 'us-east-1';
  const stackName = `kinesis-ondemand-demo-${environment}`;
  
  let cloudFormation: AWS.CloudFormation;
  let kinesis: AWS.Kinesis;
  let ecs: AWS.ECS;
  let lambda: AWS.Lambda;
  let stepFunctions: AWS.StepFunctions;
  let cloudWatch: AWS.CloudWatch;
  
  let stackOutputs: { [key: string]: string } = {};

  beforeAll(async () => {
    // Initialize AWS clients
    AWS.config.update({ region });
    cloudFormation = new AWS.CloudFormation();
    kinesis = new AWS.Kinesis();
    ecs = new AWS.ECS();
    lambda = new AWS.Lambda();
    stepFunctions = new AWS.StepFunctions();
    cloudWatch = new AWS.CloudWatch();

    // Get stack outputs
    try {
      const stackDescription = await cloudFormation.describeStacks({
        StackName: stackName,
      }).promise();

      const outputs = stackDescription.Stacks?.[0]?.Outputs || [];
      outputs.forEach(output => {
        if (output.OutputKey && output.OutputValue) {
          stackOutputs[output.OutputKey] = output.OutputValue;
        }
      });
    } catch (error) {
      console.error('Failed to get stack outputs:', error);
      throw new Error(`Stack ${stackName} not found or not accessible`);
    }
  }, 30000);

  describe('Stack Deployment', () => {
    test('stack should exist and be in a healthy state', async () => {
      const stackDescription = await cloudFormation.describeStacks({
        StackName: stackName,
      }).promise();

      expect(stackDescription.Stacks).toHaveLength(1);
      const stack = stackDescription.Stacks![0];
      expect(stack.StackStatus).toMatch(/^(CREATE_COMPLETE|UPDATE_COMPLETE)$/);
    });

    test('stack should have all required outputs', () => {
      const requiredOutputs = [
        'KinesisStreamName',
        'EcsClusterName',
        'EcsServiceName',
        'StateMachineArn',
        'ApiEndpoint',
        'DashboardUrl',
        'StepFunctionsConsoleUrl',
      ];

      requiredOutputs.forEach(outputKey => {
        expect(stackOutputs).toHaveProperty(outputKey);
        expect(stackOutputs[outputKey]).toBeTruthy();
      });
    });
  });

  describe('Kinesis Stream', () => {
    test('stream should exist and be active', async () => {
      const streamName = stackOutputs.KinesisStreamName;
      expect(streamName).toBeTruthy();

      const streamDescription = await kinesis.describeStream({
        StreamName: streamName,
      }).promise();

      expect(streamDescription.StreamDescription.StreamStatus).toBe('ACTIVE');
    });

    test('stream should be in On-Demand mode', async () => {
      const streamName = stackOutputs.KinesisStreamName;
      
      const streamDescription = await kinesis.describeStream({
        StreamName: streamName,
      }).promise();

      expect(streamDescription.StreamDescription.StreamModeDetails?.StreamMode).toBe('ON_DEMAND');
    });

    test('stream should have encryption enabled', async () => {
      const streamName = stackOutputs.KinesisStreamName;
      
      const streamDescription = await kinesis.describeStream({
        StreamName: streamName,
      }).promise();

      expect(streamDescription.StreamDescription.EncryptionType).toBe('KMS');
    });

    test('should be able to put a test record', async () => {
      const streamName = stackOutputs.KinesisStreamName;
      
      const testRecord = {
        StreamName: streamName,
        Data: JSON.stringify({
          id: 'test-record',
          timestamp: new Date().toISOString(),
          message: 'Integration test record',
        }),
        PartitionKey: 'test-partition',
      };

      const result = await kinesis.putRecord(testRecord).promise();
      expect(result.ShardId).toBeTruthy();
      expect(result.SequenceNumber).toBeTruthy();
    });
  });

  describe('ECS Resources', () => {
    test('ECS cluster should exist and be active', async () => {
      const clusterName = stackOutputs.EcsClusterName;
      expect(clusterName).toBeTruthy();

      const clusterDescription = await ecs.describeClusters({
        clusters: [clusterName],
      }).promise();

      expect(clusterDescription.clusters).toHaveLength(1);
      expect(clusterDescription.clusters![0].status).toBe('ACTIVE');
    });

    test('ECS service should exist and be active', async () => {
      const clusterName = stackOutputs.EcsClusterName;
      const serviceName = stackOutputs.EcsServiceName;
      expect(serviceName).toBeTruthy();

      const serviceDescription = await ecs.describeServices({
        cluster: clusterName,
        services: [serviceName],
      }).promise();

      expect(serviceDescription.services).toHaveLength(1);
      expect(serviceDescription.services![0].status).toBe('ACTIVE');
    });

    test('ECS service should have correct configuration', async () => {
      const clusterName = stackOutputs.EcsClusterName;
      const serviceName = stackOutputs.EcsServiceName;

      const serviceDescription = await ecs.describeServices({
        cluster: clusterName,
        services: [serviceName],
      }).promise();

      const service = serviceDescription.services![0];
      expect(service.launchType).toBe('FARGATE');
      expect(service.enableExecuteCommand).toBe(true);
      expect(service.deploymentConfiguration?.maximumPercent).toBe(200);
      expect(service.deploymentConfiguration?.minimumHealthyPercent).toBe(50);
    });

    test('ECS task definition should have correct configuration', async () => {
      const clusterName = stackOutputs.EcsClusterName;
      const serviceName = stackOutputs.EcsServiceName;

      const serviceDescription = await ecs.describeServices({
        cluster: clusterName,
        services: [serviceName],
      }).promise();

      const taskDefinitionArn = serviceDescription.services![0].taskDefinition;
      const taskDefinition = await ecs.describeTaskDefinition({
        taskDefinition: taskDefinitionArn!,
      }).promise();

      const taskDef = taskDefinition.taskDefinition!;
      expect(taskDef.networkMode).toBe('awsvpc');
      expect(taskDef.requiresCompatibilities).toContain('FARGATE');
      expect(taskDef.cpu).toBe('1024');
      expect(taskDef.memory).toBe('2048');
      expect(taskDef.containerDefinitions).toHaveLength(1);

      const container = taskDef.containerDefinitions![0];
      expect(container.essential).toBe(true);
      expect(container.portMappings).toHaveLength(1);
      expect(container.portMappings![0].containerPort).toBe(8080);
    });
  });

  describe('Lambda Functions', () => {
    const expectedFunctions = [
      `kinesis-demo-message-processor-${environment}`,
      `kinesis-demo-cost-calculator-${environment}`,
      `kinesis-demo-stepfunctions-controller-${environment}`,
    ];

    test.each(expectedFunctions)('function %s should exist and be active', async (functionName) => {
      const functionConfig = await lambda.getFunction({
        FunctionName: functionName,
      }).promise();

      expect(functionConfig.Configuration?.State).toBe('Active');
      expect(functionConfig.Configuration?.Runtime).toBe('python3.11');
    });

    test('message processor should have Kinesis event source mapping', async () => {
      const functionName = `kinesis-demo-message-processor-${environment}`;
      const streamName = stackOutputs.KinesisStreamName;

      const eventSourceMappings = await lambda.listEventSourceMappings({
        FunctionName: functionName,
      }).promise();

      expect(eventSourceMappings.EventSourceMappings).toHaveLength(1);
      const mapping = eventSourceMappings.EventSourceMappings![0];
      expect(mapping.EventSourceArn).toContain(streamName);
      expect(mapping.State).toBe('Enabled');
      expect(mapping.BatchSize).toBe(100);
    });

    test('Step Functions controller should have correct environment variables', async () => {
      const functionName = `kinesis-demo-stepfunctions-controller-${environment}`;
      const clusterName = stackOutputs.EcsClusterName;
      const serviceName = stackOutputs.EcsServiceName;

      const functionConfig = await lambda.getFunction({
        FunctionName: functionName,
      }).promise();

      const envVars = functionConfig.Configuration?.Environment?.Variables || {};
      expect(envVars.CLUSTER_NAME).toBe(clusterName);
      expect(envVars.SERVICE_NAME).toBe(serviceName);
      expect(envVars.ENVIRONMENT).toBe(environment);
    });
  });

  describe('Step Functions', () => {
    test('state machine should exist and be active', async () => {
      const stateMachineArn = stackOutputs.StateMachineArn;
      expect(stateMachineArn).toBeTruthy();

      const stateMachine = await stepFunctions.describeStateMachine({
        stateMachineArn,
      }).promise();

      expect(stateMachine.status).toBe('ACTIVE');
      expect(stateMachine.type).toBe('STANDARD');
    });

    test('should be able to start and stop an execution', async () => {
      const stateMachineArn = stackOutputs.StateMachineArn;
      const executionName = `integration-test-${Date.now()}`;

      // Start execution
      const execution = await stepFunctions.startExecution({
        stateMachineArn,
        name: executionName,
        input: JSON.stringify({ test: true }),
      }).promise();

      expect(execution.executionArn).toBeTruthy();

      // Wait a moment
      await new Promise(resolve => setTimeout(resolve, 2000));

      // Check execution status
      const executionDescription = await stepFunctions.describeExecution({
        executionArn: execution.executionArn,
      }).promise();

      expect(executionDescription.status).toMatch(/^(RUNNING|SUCCEEDED|FAILED)$/);

      // Stop execution if still running
      if (executionDescription.status === 'RUNNING') {
        await stepFunctions.stopExecution({
          executionArn: execution.executionArn,
        }).promise();
      }
    }, 15000);
  });

  describe('API Gateway', () => {
    test('API endpoint should be accessible', async () => {
      const apiEndpoint = stackOutputs.ApiEndpoint;
      expect(apiEndpoint).toBeTruthy();

      // Test API endpoint (should return 400 for POST without proper body)
      const response = await fetch(`${apiEndpoint}demo`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
      });

      // API Gateway should respond (400 is expected for malformed request)
      expect([200, 400, 403]).toContain(response.status);
    });

    test('API should integrate with Step Functions', async () => {
      const apiEndpoint = stackOutputs.ApiEndpoint;
      const stateMachineArn = stackOutputs.StateMachineArn;

      // Start execution via API
      const response = await fetch(`${apiEndpoint}demo`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({}),
      });

      if (response.status === 200) {
        const result = await response.json();
        expect(result.executionArn).toBeTruthy();
        expect(result.status).toBe('RUNNING');

        // Stop the execution
        await stepFunctions.stopExecution({
          executionArn: result.executionArn,
        }).promise();
      } else {
        // API might return 400 or 403 depending on configuration
        expect([400, 403]).toContain(response.status);
      }
    });
  });

  describe('CloudWatch Resources', () => {
    test('dashboard should exist', async () => {
      const dashboardName = `kinesis-ondemand-demo-${environment}`;

      const dashboard = await cloudWatch.getDashboard({
        DashboardName: dashboardName,
      }).promise();

      expect(dashboard.DashboardName).toBe(dashboardName);
      expect(dashboard.DashboardBody).toBeTruthy();
    });

    test('log groups should exist', async () => {
      const expectedLogGroups = [
        '/ecs/kinesis-ondemand-demo',
        `/aws/lambda/kinesis-demo-message-processor-${environment}`,
        `/aws/lambda/kinesis-demo-cost-calculator-${environment}`,
        `/aws/lambda/kinesis-demo-stepfunctions-controller-${environment}`,
        `/aws/stepfunctions/kinesis-demo-${environment}`,
      ];

      const logs = new AWS.CloudWatchLogs({ region });

      for (const logGroupName of expectedLogGroups) {
        try {
          const logGroups = await logs.describeLogGroups({
            logGroupNamePrefix: logGroupName,
          }).promise();

          const matchingGroup = logGroups.logGroups?.find(
            group => group.logGroupName === logGroupName
          );

          if (matchingGroup) {
            expect(matchingGroup.retentionInDays).toBe(7);
          }
          // Note: Some log groups are created on first use, so we don't fail if they don't exist yet
        } catch (error) {
          console.warn(`Log group ${logGroupName} not found (may be created on first use)`);
        }
      }
    });
  });

  describe('Security Configuration', () => {
    test('ECS task should have appropriate IAM permissions', async () => {
      const clusterName = stackOutputs.EcsClusterName;
      const serviceName = stackOutputs.EcsServiceName;

      const serviceDescription = await ecs.describeServices({
        cluster: clusterName,
        services: [serviceName],
      }).promise();

      const taskDefinitionArn = serviceDescription.services![0].taskDefinition;
      const taskDefinition = await ecs.describeTaskDefinition({
        taskDefinition: taskDefinitionArn!,
      }).promise();

      const taskDef = taskDefinition.taskDefinition!;
      expect(taskDef.taskRoleArn).toBeTruthy();
      expect(taskDef.executionRoleArn).toBeTruthy();
      expect(taskDef.taskRoleArn).toContain('KinesisDemo-ECSTaskRole');
      expect(taskDef.executionRoleArn).toContain('KinesisDemo-ECSTaskExecutionRole');
    });

    test('Lambda functions should have appropriate IAM roles', async () => {
      const functionName = `kinesis-demo-stepfunctions-controller-${environment}`;

      const functionConfig = await lambda.getFunction({
        FunctionName: functionName,
      }).promise();

      expect(functionConfig.Configuration?.Role).toBeTruthy();
      expect(functionConfig.Configuration?.Role).toContain('KinesisDemo-StepFunctionsControllerRole');
    });
  });

  describe('Resource Tagging', () => {
    test('resources should have consistent tags', async () => {
      const clusterName = stackOutputs.EcsClusterName;

      const clusterDescription = await ecs.describeClusters({
        clusters: [clusterName],
        include: ['TAGS'],
      }).promise();

      const cluster = clusterDescription.clusters![0];
      const tags = cluster.tags || [];

      const projectTag = tags.find(tag => tag.key === 'Project');
      const environmentTag = tags.find(tag => tag.key === 'Environment');
      const managedByTag = tags.find(tag => tag.key === 'ManagedBy');

      expect(projectTag?.value).toBe('KinesisOnDemandDemo');
      expect(environmentTag?.value).toBe(environment);
      expect(managedByTag?.value).toBe('CDK');
    });
  });

  describe('Performance and Limits', () => {
    test('ECS service should have auto scaling configured', async () => {
      const clusterName = stackOutputs.EcsClusterName;
      const serviceName = stackOutputs.EcsServiceName;

      const autoScaling = new AWS.ApplicationAutoScaling({ region });

      const scalableTargets = await autoScaling.describeScalableTargets({
        ServiceNamespace: 'ecs',
        ResourceIds: [`service/${clusterName}/${serviceName}`],
      }).promise();

      expect(scalableTargets.ScalableTargets).toHaveLength(1);
      const target = scalableTargets.ScalableTargets![0];
      expect(target.MinCapacity).toBe(1);
      expect(target.MaxCapacity).toBe(50);
      expect(target.ScalableDimension).toBe('ecs:service:DesiredCount');
    });

    test('Lambda functions should have appropriate resource limits', async () => {
      const functions = [
        `kinesis-demo-message-processor-${environment}`,
        `kinesis-demo-cost-calculator-${environment}`,
        `kinesis-demo-stepfunctions-controller-${environment}`,
      ];

      for (const functionName of functions) {
        const functionConfig = await lambda.getFunction({
          FunctionName: functionName,
        }).promise();

        const config = functionConfig.Configuration!;
        expect(config.MemorySize).toBe(256);
        expect(config.Timeout).toBeGreaterThan(0);
        expect(config.Timeout).toBeLessThanOrEqual(300); // 5 minutes max
      }
    });
  });
});

// Helper function to run shell commands
function runCommand(command: string): string {
  try {
    return execSync(command, { encoding: 'utf8' });
  } catch (error) {
    throw new Error(`Command failed: ${command}\n${error}`);
  }
}