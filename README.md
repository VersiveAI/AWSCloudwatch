# AWS Cloudwatch

## Description

This is a [dockerized](https://www.docker.com/) Python script, which generates a report containing the analysis of CPU activity across the EC2 fleet.

The script gets information from [AWS Cloudwatch](http://docs.aws.amazon.com/cli/latest/reference/cloudwatch/get-metric-statistics.html).

## How to run

### Prerequizites

The following two filesystem entities will be mapped to a dockerized container in `ro` mode.

1. ~/.aws/
2. ~/.boto

#### Example ~/.aws/config

```
[default]
output = json
region = us-west-2
```

#### Example ~/.aws/config

```
[default]
aws_access_key_id = AK...TUA
aws_secret_access_key = AtW...KJX
```

#### Example ~/.aws/config

```
[Credentials]
aws_access_key_id = AK...TUA
aws_secret_access_key = AtW...KJX
```

### Exec

1. Install [docker](https://www.docker.com/)
2. `$ git clone git:thisscript`
3. `$ cd there`
4. `docker-compose run --rm app`
5. ./app/output/ will contain the report

## Limitations

[AWS Cloudwatch](http://docs.aws.amazon.com/cli/latest/reference/cloudwatch/get-metric-statistics.html) has internal limitation:

> The maximum number of data points returned from a single call is 1,440.

## How it works

The script generates a report between `TODAY - (22 days) : TODAY - (2 days)` _(because of the AWS CLoudwatch limitation)_. It further breaks down the time period to 30 minutes intervals and checks for CPU activity spikes using the API for [get-metric-statistics --statistics Maximum](http://docs.aws.amazon.com/cli/latest/reference/cloudwatch/get-metric-statistics.html). If CPU activity does not spike at a given percentage during the whole 20 days period, than the corresponding EC2 instance ends up in the report. See `CPUActivity` section below.

**Note:** the time interval end date was chosen to be `TODAY - (2 days)` based on the assumption that it is OK too see an EC2 instance that spikes during the last 2 days (because it might have been created during the last two days).

## Report Output Format

The report is a CSV file having the following fields:

| Name          | Description |
| ------------- | ----------- |
| Instance Id   | EC2 instance id |
| Launch Time   | EC2 instance launch time |
| Creator       | comes from Tags[‘Creator’] |
| Instance Type | EC2 instance type |
| Price         | cost per hour as per <https://aws.amazon.com/ec2/pricing/on-demand/> |
| URL           | the URL to the EC2 instance in AWS console _(copy and paste to the browser to see)_ |
| CPUActivity   | CPU activity as per the tab description |
| Tags          | EC2 instance tags |

**Note:** price information comes from <http://a0.awsstatic.com/pricing/1/ec2/linux-od.min.js>

### CPUActivity

CPUActivity is a natural number showing CPU Activity of the corresponding EC2 instance with the following caveats:

| Number | Description |
| ------:| ----------- |
| 1      | EC2 instances with constant CPU activity below 1% during the last 22 days |
| 2      | EC2 instances with constant CPU activity below 2% during the last 22 days |
| 5      | EC2 instances for which CPU activity was below 5% for each of the two consecutive 30 minutes intervals (no continuous job) |
| 1000   | No Datapoints for the EC2 instance have been reported to AWS Cloudwatch |

## Example

Instance `A` did not have a CPU activity spike of at least 1% during the last 22 days - it will end up in report with `CPUActivity = 1`.
Instance `B` did not have a CPU activity spike of at least 2% during the last 22 days - it will end up in report with `CPUActivity = 2`. Note: `B` might have spiked at `> 1%`, though.

Instance `C` had a CPU activity spike of 100% in one of the 30 minutes intervals during the last 22 days, but it did not have a CPU activity in the neighboring 30 minute interval of at least 5% - it will end up in report with `CPUActivity = 5`. See the illustration below.

```
| 1 | 2 | 3 | 4 |   # 30 minutes intervals
|...|100|...|...|   # CPU activity
```
