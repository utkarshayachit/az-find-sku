import sys
import argparse
import subprocess
import json
import math

parser = argparse.ArgumentParser(description='Find SKU')
parser.add_argument('-v','--vcpu', help='Total number of vCPUs', required=True, type=int)
parser.add_argument('-m','--memory', help='Minimum required memory in GB per vCPUs', default=0, type=int)
parser.add_argument('-l','--location', help='Location', type=str, default="eastus")
parser.add_argument('-s', '--list-skus-json', help='JSON file containing list of SKUs', type=argparse.FileType('r'))
parser.add_argument('-u', '--list-usage-json', help='JSON file containing list of usage', type=argparse.FileType('r'))

args = parser.parse_args()

if args.list_skus_json is None:
    list_skus = subprocess.check_output(["az", "vm", "list-skus", "--location", args.location, "--resource-type", "virtualMachines", "--output", "json"])
else:
    list_skus = args.list_skus_json.read()
list_skus = json.loads(list_skus)

if args.list_usage_json is None:
    list_usage = subprocess.check_output(["az", "vm", "list-usage", "--location", args.location, "--output", "json"])
else:
    list_usage = args.list_usage_json.read()
list_usage = json.loads(list_usage)

limits = {}
for usage in list_usage:
    limits[usage['name']['value']] = {
        'limit': int(usage['limit']),
        'currentValue': int(usage['currentValue'])
    }

if limits['cores']['limit'] < args.vcpu:
    print(f"Total vCPUs in region ({limits['cores']['limit']}) is less than requested vCPUs ({args.vcpu})")
    sys.exit(1)

# families with sufficient quotas
families = [key for key, value in limits.items() if value['limit'] >= args.vcpu]
if len(families) == 0:
    print(f"No SKUs found with vCPU limit less than or equal to {args.vcpu}")
    sys.exit(1)

print(f"-- Found {len(families)} SKU families with vCPU limit >= {args.vcpu}")

def get_capabilities(sku):
    capabilities = {}
    for capability in sku['capabilities']:
        capabilities[capability['name']] = capability['value']
    return capabilities

# for each family, find SKUs with sufficient memory
skus = []
for family in families:
    for sku in list_skus:
        if sku['family'] == family:
            capabilities = get_capabilities(sku)
            vcpu = int(capabilities['vCPUs'])
            memory = float(capabilities['MemoryGB'])
            if vcpu >= 1 and memory >= args.memory:
                skus.append(sku)

print(f"-- Found {len(skus)} SKUs with vCPU >= 1 and memory >= {args.memory} GB in those families")

for sku in skus:
    capabilities = get_capabilities(sku)
    vcpu = int(capabilities['vCPUs'])
    memory = float(capabilities['MemoryGB'])

    usable_vcpu = vcpu
    if args.memory > 0:
        maxVcpu = math.floor(memory / args.memory)
        usable_vcpu = min(vcpu, maxVcpu)

    nVMs = math.ceil(args.vcpu / usable_vcpu)
    if nVMs == 0 or (nVMs * vcpu) > limits[sku['family']]['limit']:
        # can't use SKU since it will exceed quota
        continue

    assert usable_vcpu * args.memory <= memory, f'usable_vcpu * args.memory ({usable_vcpu * args.memory}) > memory ({memory})'
    print(f"{sku['name']} ({sku['tier']}), number of VMs: {nVMs}, vCPUs per VM: {usable_vcpu}, memory per VM: {memory} GB, requested vCPUs: {nVMs * vcpu}")
