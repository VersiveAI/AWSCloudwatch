import logging
import csv
from ec2 import EC2

REGION = 'us-west-2'


def main():
    logging.basicConfig(
        format = "%(asctime)-15s %(levelname)s %(filename)s:%(funcName)s#%(lineno)d - %(message)s",
        level  = logging.ERROR
    )

    logger = logging.getLogger("app")
    logger.setLevel(logging.DEBUG)
    logger.info("started")

    ec2 = EC2(region = REGION)
    ec2.generateCSV()

    logger.info("finished")


if __name__ == '__main__':
    main()
