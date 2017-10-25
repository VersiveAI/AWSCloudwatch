import logging
import csv
import demjson
import itertools
import boto3
import urllib.request
import os
import os.path as op
from datetime import datetime, timedelta

OUTPUT_DIR = '../output'
REGION = 'us-west-2'
CPU_SPIKE2 = 5.0
CPU_SPIKES = [ 1.0, 2.0 ]
CPU_NO_DATAPOINTS = 1000
CPU_WEIGHT_KEY = '____cpuWeight'

EC2_PRICING_URL = "http://a0.awsstatic.com/pricing/1/ec2/linux-od.min.js"
AWS_CONSOLE_EC2_FORMAT_STRING = "https://{region}.console.aws.amazon.com/ec2/v2/home?region={region}#Instances:search={instanceId};sort=instanceState"

now = datetime.today()
StartTime = now.replace(hour =  0, minute =  0, second= 0) - timedelta(days = 22)
EndTime   = now.replace(hour = 23, minute = 59, second=59) - timedelta(days =  2)

class EC2:
    def __init__(self, region = REGION, cpuSpikes = CPU_SPIKES, cpuSpike2 = CPU_SPIKE2):
        r"""
        @param region aws-region
        @param cpuSpikes EC2 instances with constant CPU activity below 'spike' during the last 20 days will be captured
        @param cpuSpike2 EC2 instances for which CPU activity was below 'spike' for each of the two consecutive 30 minute intervals (no continuous job)
        """

        self.logger = logging.getLogger("app")
        self.region = region
        self.cpuSpikes = cpuSpikes
        self.cpuSpike2 = cpuSpike2
        self.ec2 = boto3.client('ec2')
        self.cloudwatch = boto3.client('cloudwatch')

    def __getInstances(self):
        # http://boto3.readthedocs.io/en/latest/reference/services/ec2.html#EC2.Client.describe_instances
        response = self.ec2.describe_instances(
            Filters=[
                {
                    'Name': 'instance-state-code',
                    'Values': [
                        "0",  #  0 (pending)
                        "16"  # 16 (running)
                    ]
                },
            ],
            DryRun=False,
        )
        return response

    def __getResponse(self, metric, instanceId):
        return self.cloudwatch.get_metric_statistics(
            Namespace  = 'AWS/EC2',
            MetricName = metric,
            Dimensions = [
                {
                    'Name' : 'InstanceId',
                    'Value': instanceId,
                },
            ],
            StartTime  = StartTime,
            EndTime    = EndTime,
            Period     = 1800,      # in seconds
            Statistics = [
                #'SampleCount'|'Average'|'Sum'|'Minimum'|'Maximum',
                'Maximum'
            ],
        )

    def __getCPUUtilization(self, instanceId):
        self.logger.debug("Processing EC2 instanceId = %s", instanceId)

        response = self.__getResponse(metric = 'CPUUtilization', instanceId = instanceId)

        return response['Datapoints']


    def __computeCPUActiveWeight(self, datapoints):
        if len(datapoints) == 0:
            return CPU_NO_DATAPOINTS

        # Check if CPU activity was below certain threshold

        for spike in self.cpuSpikes:
            if next( (i for i in datapoints if i['Maximum'] >= spike), None) is None:
                return spike

        # Check if there was a continuous (2 consecutive 30 min intervals) activity at self.cpuSpike2

        maxedDatapoints = sorted(
            ( i for i in datapoints if i['Maximum'] >= self.cpuSpike2 ),
            key     = lambda e: e['Timestamp'],
            reverse = True
        )

        isActive = next( \
            ( \
                val for idx, val in enumerate(maxedDatapoints) \
                if idx > 0 and \
                    maxedDatapoints[idx - 1]['Timestamp'] - val['Timestamp'] == timedelta(minutes=30) \
            ), \
            None \
        ) is not None

        return 0 if isActive else self.cpuSpike2


    def __generateCSV(self, instances, pricing, filename = None):
        r"""
        if filename is None - a standard filename will be generated for the report
        """

        if filename is None:
            if not op.exists(OUTPUT_DIR):
                os.mkdir(OUTPUT_DIR)

            reportName = "%s_%s" % (
                StartTime.strftime(r'%Y-%m-%d'),
                EndTime.strftime(r'%Y-%m-%d')
            )
            filename = op.join(OUTPUT_DIR, '%s.csv' % reportName)


        with open(filename, 'w', newline='') as csvfile:
            writer = csv.writer(csvfile, dialect = 'excel')
            writer.writerow(['Instance Id', 'Launch Time', 'Creator', 'Instance Type', 'Price', 'URL', 'CPUActivity', 'Tags'])
            for inst in instances:
                writer.writerow([
                    inst['InstanceId'],
                    inst['LaunchTime'].isoformat(),
                    next( (t.get('Value') for t in inst.get('Tags', {}) if t.get('Key') == 'Creator'), None ),
                    inst['InstanceType'],
                    pricing.get(inst['InstanceType'], 0),
                    AWS_CONSOLE_EC2_FORMAT_STRING.format(region=self.region, instanceId=inst['InstanceId']),
                    inst[CPU_WEIGHT_KEY],
                    inst.get('Tags')
                ])

        self.logger.info("Created %s", filename)


    def getActiveInstances(self):
        instances   = self.__getInstances()
        instancesId = [ i['InstanceId'] for rsrv in instances['Reservations'] for i in rsrv['Instances'] ]

        cpuActivity = { \
            instanceId : self.__computeCPUActiveWeight( self.__getCPUUtilization(instanceId) ) \
            for instanceId in instancesId \
        }

        #cpuActive    = ( k for k,v in cpuActivity.items() if v == 0 )
        cpuNotActive = [ k for k,v in cpuActivity.items() if v > 0 ]

        instancesNotActive = [ i for rsrv in instances['Reservations'] for i in rsrv['Instances'] if i['InstanceId'] in cpuNotActive ]
        for inst in instancesNotActive:
            inst[CPU_WEIGHT_KEY] = cpuActivity[inst['InstanceId']]

        return instancesNotActive


    def getEC2Pricing(self):
        with urllib.request.urlopen(EC2_PRICING_URL) as response:
            res = response.read().decode('utf-8')

        # EC2_PRICING_URL contains a jsonp callback. Strip metadata and parse it as a broken JSON
        res  = res[res.index('callback(') + len('callback(') : res.rindex(');')]
        data = demjson.decode(res)

        intermediate = (  \
            i['sizes'] for i in  \
            itertools.chain.from_iterable( ( r['instanceTypes'] for r in data['config']['regions'] if r['region'] == self.region ) )  \
        )

        pricing = {  \
            t['size'] : t['valueColumns'][0]['prices']['USD'] \
            for t in \
            itertools.chain.from_iterable( intermediate ) \
        }

        return pricing


    def generateCSV(self):
        pricing = self.getEC2Pricing()
        instancesNotActive = self.getActiveInstances()
        self.__generateCSV(instancesNotActive, pricing)
