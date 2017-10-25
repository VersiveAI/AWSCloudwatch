import csv
import demjson
import itertools
import json
import boto3
import urllib.request
from datetime import datetime, timedelta

REGION = 'us-west-2'
CPU_MAX = 5.0
CPU_SPIKE = [ 1.0, 2.0 ]
CPU_WEIGHT_KEY = '____cpuWeight'

now = datetime.today()
StartTime = now.replace(hour = 0, minute = 0, second=0) - timedelta(days = 22)
EndTime   = now.replace(hour = 23, minute = 59, second=59) - timedelta(days = 2)

ec2 = boto3.client('ec2')
cloudwatch = boto3.client('cloudwatch')

class DateTimeEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, datetime):
            return o.isoformat()

        return json.JSONEncoder.default(self, o)

def getInstances():
    # http://boto3.readthedocs.io/en/latest/reference/services/ec2.html#EC2.Client.describe_instances
    response = ec2.describe_instances(
        Filters=[
            {
                'Name': 'instance-state-code',
                'Values': [
                    "0",  #  0 (pending)
                    "16"  # 16 (running)
                ]
            },
        ],
#         InstanceIds=[
#             'string',
#         ],
        DryRun=False,
#         MaxResults=123,
#         NextToken='string'
    )
    return response

def getResponse(metric, instanceId):
    return cloudwatch.get_metric_statistics(
        Namespace  = 'AWS/EC2',
        MetricName = metric,
        Dimensions = [
            {
                'Name' : 'InstanceId',
#                 'Value': 'i-001162b98ae338043',
                'Value': instanceId,
            },
        ],
        StartTime = StartTime,
        EndTime   = EndTime,
        Period    = 1800,# * 24,
        Statistics=[
            #'SampleCount'|'Average'|'Sum'|'Minimum'|'Maximum',
            'Maximum'
        ],
#         ExtendedStatistics=[
#             'string',
#         ],
#         Unit='Seconds'|'Microseconds'|'Milliseconds'|'Bytes'|'Kilobytes'|'Megabytes'|'Gigabytes'|'Terabytes'|'Bits'|'Kilobits'|'Megabits'|'Gigabits'|'Terabits'|'Percent'|'Count'|'Bytes/Second'|'Kilobytes/Second'|'Megabytes/Second'|'Gigabytes/Second'|'Terabytes/Second'|'Bits/Second'|'Kilobits/Second'|'Megabits/Second'|'Gigabits/Second'|'Terabits/Second'|'Count/Second'|'None'
    )

def getCPUUtilization(instanceId):
    print("Processing", instanceId)

    response = getResponse(metric = 'CPUUtilization', instanceId = instanceId)

    return response['Datapoints']


def computeCPUActiveWeight(datapoints):
    if len(datapoints) == 0:
        return 1000

    # Check if CPU activity was below certain threshold

    for spike in CPU_SPIKE:
        if next( (i for i in datapoints if i['Maximum'] >= spike), None) is None:
            return spike

    # Check if there was a continuous (2 consecutive 30 min intervals) activity at CPU_MAX

    maxedDatapoints = sorted(
        ( i for i in datapoints if i['Maximum'] >= CPU_MAX ),
        key     = lambda e: e['Timestamp'],
        reverse = True
    )

    isActive = next( \
        ( val for idx, val in enumerate(maxedDatapoints) if idx > 0 and maxedDatapoints[idx - 1]['Timestamp'] - val['Timestamp'] == timedelta(minutes=30) ), \
        None \
    ) is not None

    return 0 if isActive else CPU_MAX


def getActiveInstances():
    instances = getInstances()
    instancesId = [ i['InstanceId'] for rsrv in instances['Reservations'] for i in rsrv['Instances'] ]

    cpuActivity = { \
        instanceId : computeCPUActiveWeight( getCPUUtilization(instanceId) ) \
        for instanceId in instancesId \
    }

    cpuActive = [ k for k,v in cpuActivity.items() if v == 0 ]
    cpuNotActive = [ k for k,v in cpuActivity.items() if v > 0 ]

    instancesNotActive = [ i for rsrv in instances['Reservations'] for i in rsrv['Instances'] if i['InstanceId'] in cpuNotActive ]
    for inst in instancesNotActive:
        inst[CPU_WEIGHT_KEY] = cpuActivity[inst['InstanceId']]

    #TODO: remove pbd call
    import pdb; pdb.set_trace() # <-- this is temporary!
    #TODO: end of remove pbd call

    return instancesNotActive


def generateCSV(instances, pricing):
    with open('output.csv', 'w', newline='') as csvfile:
        writer = csv.writer(csvfile, dialect = 'excel')
        writer.writerow(['Instance Id', 'Launch Time', 'Creator', 'Instance Type', 'Price', 'URL', 'CPUActivity', 'Tags'])
        for inst in instances:
            writer.writerow([
                inst['InstanceId'],
                inst['LaunchTime'].isoformat(),
                next( (t.get('Value') for t in inst.get('Tags', {}) if t.get('Key') == 'Creator'), None ),
                inst['InstanceType'],
                pricing.get(inst['InstanceType'], 0),
                "https://{region}.console.aws.amazon.com/ec2/v2/home?region={region}#Instances:search={instanceId};sort=instanceState".format(region=REGION, instanceId=inst['InstanceId']),
                inst[CPU_WEIGHT_KEY],
                inst.get('Tags')
            ])


def getEC2Pricing():
    with urllib.request.urlopen("http://a0.awsstatic.com/pricing/1/ec2/linux-od.min.js") as response:
        res = response.read().decode('utf-8')

    res = res[res.index('callback(') + len('callback(') : res.rindex(');')]
    data = demjson.decode(res)

    intermediate = (  \
        i['sizes'] for i in  \
        itertools.chain.from_iterable( ( r['instanceTypes'] for r in data['config']['regions'] if r['region'] == REGION ) )  \
    )

    pricing = {  \
        t['size'] : t['valueColumns'][0]['prices']['USD'] \
        for t in \
        itertools.chain.from_iterable( intermediate ) \
    }

    return pricing


def main():
    pricing = getEC2Pricing()

    instancesNotActive = getActiveInstances()

    output = json.dumps(instancesNotActive, cls=DateTimeEncoder)
    with open('output.json', 'w') as f:
        f.write(output)

    generateCSV(instancesNotActive, pricing)

    #TODO: remove pbd call
    import pdb; pdb.set_trace() # <-- this is temporary!
    #TODO: end of remove pbd call


if __name__ == '__main__':
    main()
