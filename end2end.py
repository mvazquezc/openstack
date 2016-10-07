#!/bin/python
import json
from keystoneauth1.identity import v3
from keystoneauth1 import session
from novaclient import client
import ConfigParser
import time
import socket
import paramiko

cnf = ConfigParser.ConfigParser()
cnf.read('/path/to/conf/file')
conf_ostack_auth_url = cnf.get('config', 'ostack_auth_url')
conf_ostack_user = cnf.get('config', 'ostack_user')
conf_ostack_user_pwd = cnf.get('config', 'ostack_user_pwd')
conf_ostack_user_pkey = cnf.get('config', 'ostack_user_pkey')
conf_ostack_user_pkey_name = cnf.get('config', 'ostack_user_pkey_name')
conf_ostack_project_name = cnf.get('config', 'ostack_project_name')
conf_ostack_user_domain_id = cnf.get('config', 'ostack_user_domain_id')
conf_ostack_project_domain_id = cnf.get('config', 'ostack_project_domain_id')
conf_nova_image_name = cnf.get('config', 'nova_image_name')
conf_nova_image_user = cnf.get('config', 'nova_image_user')
conf_nova_flavor = cnf.get('config', 'nova_flavor')
conf_neutron_vm_network = cnf.get('config', 'neutron_vm_network')
conf_nova_instance_name = cnf.get('config', 'nova_instance_name')
conf_default_sg_name = cnf.get('config', 'default_sg_name')
conf_ssh_sg_name = cnf.get('config', 'ssh_sg_name')
conf_commands = cnf.get('config', 'commands')
conf_commands = conf_commands.split(',')

try:
    auth = v3.Password(auth_url=conf_ostack_auth_url, username=conf_ostack_user, password=conf_ostack_user_pwd, project_name=conf_ostack_project_name, user_domain_id=conf_ostack_user_domain_id, project_domain_id=conf_ostack_project_domain_id)
    sess = session.Session(auth=auth)
    nova = client.Client("2.1", session=sess)
except:
    raise SystemError('Cannot get a session')

# Get a free floating IP
unused_ips = [addr for addr in nova.floating_ips.list() if addr.instance_id is None]
floating_ip = unused_ips[0].ip
# Get image 
image = nova.images.find(name=conf_nova_image_name)
# Get flavor
flavor = nova.flavors.find(name=conf_nova_flavor)
# Get network
network = nova.networks.find(label=conf_neutron_vm_network)
# Instantiate VM
server = nova.servers.create(name = conf_nova_instance_name, image = image.id, flavor = flavor.id, nics = [{'net-id':network.id}], key_name = conf_ostack_user_pkey_name)
# Check server status
server = nova.servers.find(id=server.id)
# Wait for server startup
t = 0
while server.status != 'ACTIVE':
    time.sleep(2)
    if t > 10:
        raise SystemError('Instance taking too long to be ACTIVE')
    t += 1
    server = nova.servers.find(id=server.id)
# Assign a floating ip to the server
server.add_floating_ip(floating_ip)
# Get default security group
default_sg = nova.security_groups.find(name=conf_default_sg_name)
# Get SSH security group
ssh_sg = nova.security_groups.find(name=conf_ssh_sg_name)
# Assign security groups to the server
server.add_security_group(default_sg.id)
server.add_security_group(ssh_sg.id)

t = 0
online = False
s = socket.socket()
s.settimeout(5)
while online == False:
    try:
        s.connect((floating_ip,22))
    except socket.error:
        t += 1
        time.sleep(2)
        if t > 10:
            raise SystemError('Instance is not accesible via SSH')
    else:
        s.close()
        online = True
        time.sleep(2)

try:
    ssh_key = paramiko.RSAKey.from_private_key_file(conf_ostack_user_pkey)
    ssh_client = paramiko.SSHClient()
    ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh_client.connect(hostname = floating_ip, username = conf_nova_image_user, pkey = ssh_key)
    results = []
    for command in conf_commands:
        stdin , stdout, stderr = ssh_client.exec_command(command)
        results.append({ 'command': command, 'exit_level': stdout.channel.recv_exit_status()})
    ssh_client.close()
    server.delete()
    results_json = '{ "results": ' + json.dumps(results, indent=4) + '}'
    print results_json
except:
    server.delete()
    raise SystemError('Error connecting to the instance via ssh')

