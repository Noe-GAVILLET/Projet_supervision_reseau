from snmp_utils import get_metrics
print(get_metrics("192.168.1.25", "public", 161, "interfaces"))