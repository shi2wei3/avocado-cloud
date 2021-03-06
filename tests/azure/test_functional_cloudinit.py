import os
import re
import time
from avocado import Test
from avocado import main
from avocado_cloud.app import Setup
from avocado_cloud.app.azure import AzureAccount
from avocado_cloud.app.azure import AzureNIC
from avocado_cloud.app.azure import AzurePublicIP
from avocado_cloud.app.azure import AzureNicIpConfig
from avocado_cloud.app.azure import AzureImage
from distutils.version import LooseVersion
from avocado_cloud.utils.utils_azure import command

BASEPATH = os.path.abspath(__file__ + "/../../../")


class CloudinitTest(Test):
    def setUp(self):
        account = AzureAccount(self.params)
        account.login()
        self.project = self.params.get("rhel_ver", "*/VM/*")
        self.case_short_name = re.findall(r"Test.(.*)", self.name.name)[0]
        self.pwd = os.path.abspath(os.path.dirname(__file__))
        if self.case_short_name == "test_cloudinit_provision_gen2_vm":
            if LooseVersion(self.project) < LooseVersion('7.8'):
                self.cancel(
                    "Skip case because RHEL-{} ondemand image doesn't support gen2".format(self.project))
            cloud = Setup(self.params, self.name, size="DS2_v2")
        else:
            cloud = Setup(self.params, self.name)
        if self.case_short_name == "test_cloudinit_provision_gen2_vm":
            self.image = AzureImage(self.params, generation="V2")
            self.image.create()
            cloud.vm.image = self.image.name
            cloud.vm.vm_name += "-gen2"
            cloud.vm.use_unmanaged_disk = False
        self.vm = cloud.vm
        self.package = self.params.get("packages", "*/Other/*")
        if self.case_short_name in [
                "test_cloudinit_login_with_password",
                "test_cloudinit_login_with_publickey",
                "test_cloudinit_save_and_handle_customdata_script",
                "test_cloudinit_save_and_handle_customdata_cloudinit_config",
                "test_cloudinit_assign_identity",
        ]:
            if self.vm.exists():
                self.vm.delete()
            self.session = cloud.init_session()
            return
        if self.case_short_name == \
                "test_cloudinit_provision_vm_with_multiple_nics":
            self.vm.vm_name += "2nics"
            if self.vm.exists():
                self.vm.delete()
            publicip_name = self.vm.vm_name + "publicip"
            publicip = AzurePublicIP(self.params, name=publicip_name)
            if not publicip.exists():
                publicip.create()
            nic_name_list = []
            for n in range(0, 2):
                nic_name = "{}nic{}".format(self.vm.vm_name, n)
                subnet = self.vm.subnet if n == 0 else self.vm.subnet + str(n)
                n_publicip = publicip_name if n == 0 else None
                nic = AzureNIC(self.params,
                               name=nic_name,
                               subnet=subnet,
                               vnet=self.vm.vnet_name,
                               publicip=n_publicip)
                if not nic.exists():
                    nic.create()
                nic_name_list.append(nic_name)
            self.vm.nics = ' '.join(nic_name_list)
            self.session = cloud.init_session()
            return
        if self.case_short_name == "test_cloudinit_provision_vm_with_sriov_nic":
            self.vm.vm_name += "sriov"
            if self.vm.exists():
                self.vm.delete()
            publicip_name = self.vm.vm_name + "publicip"
            publicip = AzurePublicIP(self.params, name=publicip_name)
            if not publicip.exists():
                publicip.create()
            self.vm.nics = "{}nic".format(self.vm.vm_name)
            nic = AzureNIC(self.params,
                           name=self.vm.nics,
                           subnet=self.vm.subnet,
                           vnet=self.vm.vnet_name,
                           publicip=publicip_name,
                           sriov=True)
            if not nic.exists():
                nic.create()
            self.session = cloud.init_session()
            self.vm.size = "Standard_D3_v2"
            return
        if self.name.name.endswith("test_cloudinit_provision_vm_with_ipv6"):
            self.vm.vm_name += "ipv6"
            if self.vm.exists():
                self.vm.delete()
            publicip_name = self.vm.vm_name + "publicip"
            publicip = AzurePublicIP(self.params,
                                     name=publicip_name)
            if not publicip.exists():
                publicip.create()
            self.vm.nics = "{}nic".format(self.vm.vm_name)
            nic = AzureNIC(self.params,
                           name=self.vm.nics,
                           subnet=self.vm.subnet,
                           vnet=self.vm.vnet_name,
                           publicip=publicip_name)
            if not nic.exists():
                nic.create()
            ipv6_config = AzureNicIpConfig(self.params,
                                           name=self.vm.nics+"ipv6",
                                           nic_name=self.vm.nics,
                                           ip_version="IPv6")
            if not ipv6_config.exists():
                ipv6_config.create()
            self.session = cloud.init_session()
            return
        self.session = cloud.init_vm()
        if self.case_short_name == "test_cloudinit_upgrade_downgrade_package":
            rhel7_old_pkg_url = "http://download.eng.bos.redhat.com/brewroot/vol/rhel-7/packages/cloud-init/18.2/1.el7/x86_64/cloud-init-18.2-1.el7.x86_64.rpm"
            rhel8_old_pkg_url = "http://download.eng.bos.redhat.com/brewroot/vol/rhel-8/packages/cloud-init/18.2/1.el8/noarch/cloud-init-18.2-1.el8.noarch.rpm"
            try:
                self.assertEqual(0, self.session.cmd_status_output("ls /tmp/{}".format(self.package))[0],
                                 "No new pakcage in guest VM")
                import requests
                if str(self.project).startswith('7'):
                    old_pkg_url = rhel7_old_pkg_url
                elif str(self.project).startswith('8'):
                    old_pkg_url = rhel8_old_pkg_url
                self.old_pkg = old_pkg_url.split('/')[-1]
                if not os.path.exists("/tmp/{}".format(self.old_pkg)):
                    r = requests.get(old_pkg_url, allow_redirects=True)
                    open("/tmp/{}".format(self.old_pkg), 'wb').write(r.content)
                self.session.copy_files_to(
                    local_path="/tmp/{}".format(self.old_pkg),
                    remote_path="/tmp/{}".format(self.old_pkg))
                self.assertEqual(0, self.session.cmd_status_output("ls /tmp/{}".format(self.old_pkg))[0],
                                 "No old pakcage in guest VM")
            except:
                self.cancel(
                    "No old or new package in guest VM. Skip this case.")

    def test_cloudinit_login_with_password(self):
        """
        :avocado: tags=tier1,cloudinit
        RHEL7-87233: WALA-TC: [Cloudinit] VM can successfully login
        after provisioning(with password authentication)
        1. Create a VM with only password authentication
        2. Login with password, should have sudo privilege
        """
        self.log.info(
            "RHEL7-87233: WALA-TC: [Cloudinit] VM can successfully login "
            "after provisioning(with password authentication)")
        self.vm.ssh_key_value = None
        self.vm.generate_ssh_keys = None
        self.vm.authentication_type = "password"
        self.vm.create(wait=True)
        self.session.connect(authentication="password")
        self.assertEqual(self.vm.vm_username,
                         self.session.cmd_output("whoami"),
                         "Fail to login with password")
        self.assertIn(
            "%s ALL=(ALL) NOPASSWD:ALL" % self.vm.vm_username,
            self.session.cmd_output(
                "sudo cat /etc/sudoers.d/90-cloud-init-users"),
            "No sudo privilege")

    def test_cloudinit_login_with_publickey(self):
        """
        :avocado: tags=tier1,cloudinit,cloud_utils_growpart,dependencies
        RHEL7-87453: WALA-TC: [Cloudinit] VM can successfully login
        after provisioning(with publickey authentication)
        1. Create a VM with only public key authentication
        2. Login with publickey, should have sudo privilege
        """
        self.log.info(
            "RHEL7-87453: WALA-TC: [Cloudinit] VM can successfully login "
            "after provisioning(with publickey authentication)")
        self.vm.create(wait=True)
        self.session.connect(authentication="publickey")
        self.assertEqual(self.vm.vm_username,
                         self.session.cmd_output("whoami"),
                         "Fail to login with publickey")
        self.assertIn(
            "%s ALL=(ALL) NOPASSWD:ALL" % self.vm.vm_username,
            self.session.cmd_output(
                "sudo cat /etc/sudoers.d/90-cloud-init-users"),
            "No sudo privilege")
        # Collect /var/log/cloud-init.log and /var/log/messages
        try:
            self.session.cmd_output("mkdir -p /tmp/logs")
            self.session.cmd_output(
                "sudo cp /var/log/cloud-init.log /tmp/logs/")
            self.session.cmd_output("sudo cp /var/log/messages /tmp/logs/")
            self.session.cmd_output("sudo chmod 644 /tmp/logs/*")
            host_logpath = os.path.dirname(self.job.logfile) + "/logs"
            command("mkdir -p {}".format(host_logpath))
            self.session.copy_files_from("/tmp/logs/*", host_logpath)
        except:
            pass

    def test_cloudinit_verify_hostname(self):
        """
        :avocado: tags=tier1,cloudinit
        RHEL7-87350: WALA-TC: [Cloudinit] Successfully set VM hostname
        1. Verify VM hostname
        """
        self.log.info(
            "RHEL7-87350: WALA-TC: [Cloudinit] Successfully set VM hostname")
        cmd_list = [
            'hostname', 'nmcli general hostname', 'hostnamectl|grep Static'
        ]
        for cmd in cmd_list:
            self.assertIn(self.vm.vm_name, self.session.cmd_output(cmd),
                          "'%s': Hostname is not correct" % cmd)

    def test_cloudinit_create_ovfenv_under_waagent_folder(self):
        """
        :avocado: tags=tier1,cloudinit
        RHEL7-87367: WALA-TC: [Cloudinit] Create ovf-env.xml under
        /var/lib/waagent folder
        Check if file "/var/lib/waagent/ovf-env.xml" exists
        """
        self.log.info("RHEL7-87367: WALA-TC: [Cloudinit] Create ovf-env.xml "
                      "under /var/lib/waagent folder")
        self.assertEqual(
            self.session.cmd_status_output(
                "sudo ls /var/lib/waagent/ovf-env.xml")[0], 0,
            "File /var/lib/waagent/ovf-env.xml doesn't exist")

    def test_cloudinit_publish_hostname_to_dns(self):
        """
        :avocado: tags=tier1,cloudinit
        RHEL7-87459: WALA-TC: [Cloudinit] Publish VM hostname to DNS server
        1. Get FQDN hostname
        2. Check FQDN name can be resolved by DNS server
        """
        self.log.info("RHEL7-87459: WALA-TC: [Cloudinit] Publish VM \
hostname to DNS server")
        self.assertIn(".internal.cloudapp.net",
                      self.session.cmd_output("hostname -f"),
                      "Cannot get whole FQDN")
        self.assertNotIn(
            "NXDOMAIN",
            self.session.cmd_output("nslookup %s" % self.vm.vm_name),
            "Fail to publish hostname to DNS")

    def test_cloudinit_regenerate_sshd_keypairs(self):
        """
        :avocado: tags=tier2,cloudinit
        RHEL7-87462: WALA-TC: [Cloudinit] Regenerate sshd keypairs
        1. Verify cloud.cfg: ssh_deletekeys:   1
        2. Deprovision image. Create a new VM base on this image
        3. Login and compare the md5 of the new and old sshd_host* files.
           Should regenerate them.
        """
        self.log.info(
            "RHEL7-87462: WALA-TC: [Cloudinit] Regenerate sshd keypairs")
        # Login with root
        self.session.cmd_output("sudo /usr/bin/cp -a /home/{0}/.ssh /root/;"
                                "sudo chown -R root:root /root/.ssh".format(
                                    self.vm.vm_username))
        self.session.close()
        origin_username = self.vm.vm_username
        self.vm.vm_username = "root"
        self.session.connect(authentication="publickey")
        # Verify cloud.cfg ssh_deletekeys:   0
        self.assertEqual(
            self.session.cmd_status_output(
                "grep -E '(ssh_deletekeys: *1)' /etc/cloud/cloud.cfg")[0], 0,
            "ssh_deletekeys: 1 is not in cloud.cfg")
        old_md5 = self.session.cmd_output("md5sum /etc/ssh/ssh_host_rsa_key "
                                          "/etc/ssh/ssh_host_ecdsa_key "
                                          "/etc/ssh/ssh_host_ed25519_key")
        # Deprovision image
        if self.session.cmd_status_output(
                "systemctl is-enabled waagent")[0] == 0:
            mode = "cloudinit_wala"
        else:
            mode = "cloudinit"
        script = "deprovision_package.sh"
        self.session.copy_files_to(local_path="{}/../../scripts/{}".format(
            self.pwd, script),
            remote_path="/tmp/{}".format(script))
        ret, output = self.session.cmd_status_output(
            "/bin/bash /tmp/{} all {} {}".format(script, mode, origin_username))
        self.assertEqual(ret, 0, "Deprovision VM failed.\n{0}".format(output))
        self.session.close()
        # Delete VM
        osdisk = self.vm.properties["storageProfile"]["osDisk"]["vhd"]["uri"]
        self.vm.delete()
        self.vm.image = osdisk
        self.vm.vm_username = origin_username
        self.vm.os_disk_name += "-new"
        self.vm.create()
        self.session.connect()
        new_md5 = self.session.cmd_output(
            "sudo md5sum /etc/ssh/ssh_host_rsa_key "
            "/etc/ssh/ssh_host_ecdsa_key "
            "/etc/ssh/ssh_host_ed25519_key")
        self.assertNotEqual(old_md5, new_md5,
                            "The ssh host keys are not regenerated.")

    def test_cloudinit_save_and_handle_customdata_script(self):
        """
        :avocado: tags=tier2,cloudinit
        RHEL7-87464: WALA-TC: [Cloudinit] Save and handle customdata(script)
        1. Create VM with custom data
        2. Get CustomData from ovf-env.xml, decode it and compare with
           original custom data file
        3. Check if custom data script is executed
        """
        self.log.info("RHEL7-87464: WALA-TC: [Cloudinit] Save and handle \
customdata(script)")
        # Prepare custom script
        script = """\
#!/bin/bash
echo 'teststring' >> /var/log/test.log\
"""
        with open("/tmp/customdata.sh", 'w') as f:
            f.write(script)
        # 1. Create VM with custom data
        self.vm.custom_data = "/tmp/customdata.sh"
        self.vm.create()
        self.session.connect()
        # 2. Compare custom data
        custom_data = self.session.cmd_output(
            "sudo grep -o -P '(?<=CustomData>).*(?=<.*CustomData>)' "
            "/var/lib/waagent/ovf-env.xml|base64 -d")
        self.assertEqual(
            custom_data,
            self.session.cmd_output(
                "sudo cat /var/lib/cloud/instance/user-data.txt"),
            "Custom data in ovf-env.xml is not equal to user-data.txt")
        # 3. Check if custom data script is executed
        self.assertEqual("teststring",
                         self.session.cmd_output("cat /var/log/test.log"),
                         "The custom data script is not executed correctly.")

    def test_cloudinit_save_and_handle_customdata_cloudinit_config(self):
        """
        :avocado: tags=tier2,cloudinit
        RHEL7-91623: WALA-TC: [Cloudinit] Save and handle customdata
        (cloud-init configuration)
        1. Create VM with custom data
        2. Get CustomData from ovf-env.xml, decode it and compare with
           original custom data file
        3. Check if the new cloud-init configuration is handled correctly
        """
        self.log.info(
            "RHEL7-91623: WALA-TC: [Cloudinit] Save and handle customdata"
            "(cloud-init configuration)")
        # Prepare custom data
        customdata_ori = """\
#cloud-config
cloud_config_modules:
 - mounts
 - locale
 - set-passwords
 - yum-add-repo
 - disable-ec2-metadata
 - runcmd
"""
        with open("/tmp/customdata.conf", 'w') as f:
            f.write(customdata_ori)
        # 1. Create VM with custom data
        self.vm.custom_data = "/tmp/customdata.conf"
        self.vm.create()
        self.session.connect()
        # 2. Compare custom data
        custom_data = self.session.cmd_output(
            "sudo grep -o -P '(?<=CustomData>).*(?=<.*CustomData>)' "
            "/var/lib/waagent/ovf-env.xml|base64 -d")
        self.assertEqual(
            custom_data,
            self.session.cmd_output(
                "sudo cat /var/lib/cloud/instance/user-data.txt"),
            "Custom data in ovf-env.xml is not equal to user-data.txt")
        # 3. Check if the new cloud-init configuration is handled correctly
        # (There should be 6 modules ran in cloud-init.log)
        output = self.session.cmd_output(
            "sudo grep 'running modules for config' "
            "/var/log/cloud-init.log -B 10")
        self.assertIn("Ran 6 modules", output,
                      "The custom data is not handled correctly")

    def test_cloudinit_auto_extend_root_partition_and_filesystem(self):
        """
        :avocado: tags=tier1,cloudinit,cloud_utils_growpart
        RHEL7-91512: WALA-TC: [Cloudinit] Auto extend root partition and
        filesystem
        1. Install cloud-utils-growpart gdisk if not installed(bug 1447177)
        2. Check os disk and fs capacity
        3. Stop VM. Enlarge os disk
        4. Start VM and login. Check os disk and fs capacity
        """
        self.log.info("RHEL7-91512: WALA-TC: [Cloudinit] Auto extend root \
partition and filesystem")
        # 1. Install cloud-utils-growpart gdisk
        if self.session.cmd_status_output(
                "rpm -q cloud-utils-growpart gdisk")[0] != 0:
            self.session.cmd_output("sudo rpm -ivh /root/rhui-azure-*.rpm")
            self.session.cmd_output(
                "sudo yum install -y cloud-utils-growpart gdisk")
            if self.session.cmd_status_output(
                    "rpm -q cloud-utils-growpart gdisk")[0] != 0:
                self.fail("Cannot install cloud-utils-growpart gdisk packages")
        # 2. Check os disk and fs capacity
        boot_dev = self.session.cmd_output("mount|grep 'boot ' | cut -c6-8")
        partition = self.session.cmd_output(
            "find /dev/ -name {}[0-9]|sort|tail -n 1".format(boot_dev))
        dev_size = self.session.cmd_output(
            "lsblk /dev/{0} --output NAME,SIZE -r"
            "|grep -o -P '(?<={0} ).*(?=G)'".format(boot_dev))
        fs_size = self.session.cmd_output(
            "df {} --output=size -h|grep -o '[0-9.]\+'".format(partition))
        os_disk_size = self.vm.properties["storageProfile"]["osDisk"][
            "diskSizeGb"]
        self.assertAlmostEqual(
            first=float(dev_size),
            second=float(os_disk_size),
            delta=1,
            msg="Device size is incorrect. Raw disk: %s, real: %s" %
            (dev_size, os_disk_size))
        self.assertAlmostEqual(first=float(fs_size),
                               second=float(os_disk_size),
                               delta=1.5,
                               msg="Filesystem size is incorrect. "
                               "FS: %s, real: %s" % (fs_size, os_disk_size))
        # 3. Enlarge os disk size
        self.vm.stop()
        new_os_disk_size = os_disk_size + 2
        self.vm.osdisk_resize(new_os_disk_size)
        # 4. Start VM and login. Check os disk and fs capacity
        self.vm.start()
        self.session.connect()
        boot_dev = self.session.cmd_output("mount|grep 'boot ' | cut -c6-8")
        partition = self.session.cmd_output(
            "find /dev/ -name {}[0-9]|sort|tail -n 1".format(boot_dev))
        new_dev_size = self.session.cmd_output(
            "lsblk /dev/{0} --output NAME,SIZE -r"
            "|grep -o -P '(?<={0} ).*(?=G)'".format(boot_dev))
        new_fs_size = self.session.cmd_output(
            "df {} --output=size -h|grep -o '[0-9]\+'".format(partition))
        self.assertEqual(
            int(new_dev_size), int(new_os_disk_size),
            "New device size is incorrect. "
            "Device: %s, real: %s" % (new_dev_size, new_os_disk_size))
        self.assertAlmostEqual(first=float(new_fs_size),
                               second=float(new_os_disk_size),
                               delta=1.5,
                               msg="New filesystem size is incorrect. "
                               "FS: %s, real: %s" %
                               (new_fs_size, new_os_disk_size))

    def test_cloudinit_verify_temporary_disk_mount_point(self):
        """
        :avocado: tags=tier1,cloudinit
        RHEL-131780: WALA-TC: [Cloudinit] Check temporary disk mount point
        1. New VM. Check if temporary disk is mounted
        2. Restart VM from azure cli. Check mount point again
        """
        self.log.info("RHEL-131780: WALA-TC: [Cloudinit] Check temporary \
disk mount point")
        boot_dev = self.session.cmd_output("mount|grep 'boot ' | cut -c1-8")
        temp_dev = '/dev/sda' if boot_dev == '/dev/sdb' else '/dev/sdb'
        status = self.session.cmd_status_output(
            "mount|grep {}1".format(temp_dev))[0]
        self.log.info(
            self.session.cmd_output("sudo fdisk -l {}".format(temp_dev)))
        self.assertEqual(
            status, 0, "After create VM, {}1 is not mounted".format(temp_dev))
        # Redeply VM (move to another host. The ephemeral disk will be new)
        self.vm.redeploy()
        self.session.connect()
        status = self.session.cmd_status_output(
            "mount|grep {}1".format(temp_dev))[0]
        self.log.info(
            self.session.cmd_output("sudo fdisk -l {}".format(temp_dev)))
        self.assertEqual(
            status, 0,
            "After redeploy VM, {}1 is not mounted".format(temp_dev))

    def test_cloudinit_check_service_status(self):
        """
        :avocado: tags=tier1,cloudinit
        RHEL-188130: WALA-TC: [Cloudinit] Check cloud-init service status
        The 4 cloud-init services status should be "active"
        """
        self.log.info(
            "RHEL-188130: WALA-TC: [Cloudinit] Check cloud-init service status")
        service_list = ['cloud-init-local',
                        'cloud-init',
                        'cloud-config',
                        'cloud-final']
        for service in service_list:
            output = self.session.cmd_output(
                "sudo systemctl is-active {}".format(service))
            self.assertEqual(output, 'active',
                             "{} status is not correct: {}".format(service, output))

    def test_cloudinit_check_critical_log(self):
        """
        :avocado: tags=tier1,cloudinit
        RHEL-188029: WALA-TC: [Cloudinit] Check CRITICAL cloud-init log
        Check cloud-init log. There shouldn't be CRITICAL logs.
        """
        self.log.info(
            "RHEL-188029: WALA-TC: [Cloudinit] Check CRITICAL cloud-init log")
        output = self.session.cmd_output(
            "sudo grep -i 'critical' /var/log/cloud-init.log")
        self.assertEqual(
            "", output, "There're CRITICAL logs: {0}".format(output))

    def test_cloudinit_check_cloudinit_log(self):
        """
        :avocado: tags=tier2,cloudinit
        RHEL-151376: WALA-TC: [Cloudinit] Check cloud-init log
        Check cloud-init log. There shouldn't be unexpected error logs.
        """
        self.log.info("RHEL-151376: WALA-TC: [Cloudinit] Check cloud-init log")
        with open("{}/data/azure/ignore_cloudinit_messages".format(BASEPATH),
                  'r') as f:
            ignore_message_list = f.read().split('\n')
        output = self.session.cmd_output(
            "sudo grep -iE -w 'err.*|fail.*|warn.*|unexpected.*|traceback.*' /var/log/cloud-init.log|grep -vE '{0}'"
            .format('|'.join(ignore_message_list)))
        self.assertEqual("", output, "There're error logs: {0}".format(output))

    def test_cloudinit_assign_identity(self):
        """
        :avocado: tags=tier2,cloudinit
        RHEL-152186: WALA-TC: [Cloudinit] Assign identity
        CVE BZ#1680165
        """
        self.log.info("RHEL-152186: WALA-TC: [Cloudinit] Assign identity")
        self.vm.assign_identity = True
        self.vm.create(wait=True)
        self.session.connect()
        self.assertEqual(
            '1',
            self.session.cmd_output(
                "cat /home/{0}/.ssh/authorized_keys|wc -l".format(
                    self.vm.vm_username)),
            "More then 1 public keys in /home/{0}/.ssh/authorized_keys".format(
                self.vm.vm_username))

    def test_cloudinit_check_networkmanager_dispatcher(self):
        """
        :avocado: tags=tier2,cloudinit
        RHEL-170749: WALA-TC: [Cloudinit] Check NetworkManager dispatcher
        BZ#1707725
        """
        self.log.info(
            "RHEL-170749: WALA-TC: [Cloudinit] Check NetworkManager dispatcher"
        )
        self.session.cmd_output("sudo su -")
        # 1. cloud-init is enabled
        self.assertEqual(
            self.session.cmd_status_output("ls /run/cloud-init/enabled")[0], 0,
            "No /run/cloud-init/enabled when cloud-init is enabled")
        self.session.cmd_output("rm -rf /run/cloud-init/dhclient.hooks/*.json")
        self.session.cmd_output("systemctl restart NetworkManager")
        time.sleep(3)
        self.assertEqual(
            self.session.cmd_status_output(
                "ls /run/cloud-init/dhclient.hooks/*.json")[0], 0,
            "Cannot run cloud-init if it is enabled")
        # 2. cloud-init is disabled
        self.session.cmd_output("mv /run/cloud-init/enabled /tmp/")
        self.session.cmd_output("rm -f /run/cloud-init/dhclient.hooks/*.json")
        self.session.cmd_output("systemctl restart NetworkManager")
        time.sleep(3)
        self.assertNotEqual(
            self.session.cmd_status_output(
                "sudo ls /run/cloud-init/dhclient.hooks/*.json")[0], 0,
            "Should not run cloud-init if it is not enabled")

    def _cloudinit_auto_resize_partition(self, label):
        """
        :param label: msdos/gpt
        """
        self.session.cmd_output("sudo su -")
        self.assertEqual(
            self.session.cmd_status_output("which growpart")[0], 0,
            "No growpart command.")
        device = "/tmp/testdisk"
        if "/dev" not in device:
            self.session.cmd_output("rm -f {}".format(device))
        self.session.cmd_output("truncate -s 2G {}".format(device))
        self.session.cmd_output(
            "parted -s {} mklabel {}".format(device, label))
        part_type = "primary" if label == "msdos" else ""
        # 1 partition
        self.session.cmd_output(
            "parted -s {} mkpart {} xfs 0 1000".format(device, part_type))
        self.session.cmd_output("parted -s {} print".format(device))
        self.assertEqual(
            self.session.cmd_status_output("growpart {} 1".format(device))[0],
            0, "Fail to run growpart")
        self.assertEqual(
            "2147MB",
            self.session.cmd_output(
                "parted -s %s print|grep ' 1 '|awk '{print $3}'" % device),
            "Fail to resize partition")
        # 2 partitions
        self.session.cmd_output("parted -s {} rm 1".format(device))
        self.session.cmd_output(
            "parted -s {} mkpart {} xfs 0 1000".format(device, part_type))
        self.session.cmd_output(
            "parted -s {} mkpart {} xfs 1800 1900".format(device, part_type))
        self.session.cmd_output("parted -s {} print".format(device))
        exit_status, output = self.session.cmd_status_output(
            "growpart {} 1".format(device))
        self.assertEqual(exit_status, 0,
                         "Run growpart failed: {}".format(output))
        self.assertEqual(
            "1800MB",
            self.session.cmd_output(
                "parted -s %s print|grep ' 1 '|awk '{print $3}'" % device),
            "Fail to resize partition")

    def test_cloudinit_auto_resize_partition_in_gpt(self):
        """
        :avocado: tags=tier1,cloud_utils_growpart
        RHEL-171053: CLOUDINIT-TC: [cloud-utils-growpart] Auto resize\
                     partition in gpt
        BZ#1695091
        """
        self.log.info("RHEL-171053: CLOUDINIT-TC: [cloud-utils-growpart] \
Auto resize partition in gpt")
        self._cloudinit_auto_resize_partition("gpt")

    def test_cloudinit_auto_resize_partition_in_mbr(self):
        """
        :avocado: tags=tier1,cloud_utils_growpart
        RHEL-188633: CLOUDINIT-TC: [cloud-utils-growpart] Auto resize\
                     partition in MBR
        """
        self.log.info("RHEL-188633: CLOUDINIT-TC: [cloud-utils-growpart] \
Auto resize partition in gpt")
        self._cloudinit_auto_resize_partition("msdos")

    def test_cloudinit_start_sector_equal_to_partition_size(self):
        """
        :avocado: tags=tier1,cloud_utils_growpart
        RHEL-171175: CLOUDINIT-TC: [cloud-utils-growpart] Start sector equal
                     to partition size
        BZ#1593451
        """
        self.log.info("RHEL-171175: CLOUDINIT-TC: [cloud-utils-growpart] \
Start sector equal to partition size")
        self.session.cmd_output("sudo su -")
        self.assertEqual(
            self.session.cmd_status_output("which growpart")[0], 0,
            "No growpart command.")
        device = "/tmp/testdisk"
        if "/dev" not in device:
            self.session.cmd_output("rm -f {}".format(device))
        self.session.cmd_output("truncate -s 2G {}".format(device))
        size = "1026048"
        self.session.cmd_output("""
cat > partitions.txt <<EOF
# partition table of {0}
unit: sectors

{0}1 : start= 2048, size= 1024000, Id=83
{0}2 : start= {1}, size= {1}, Id=83
EOF""".format(device, size))
        self.session.cmd_output("sfdisk {} < partitions.txt".format(device))
        self.session.cmd_output("growpart {} 2".format(device))
        start = self.session.cmd_output(
            "parted -s %s unit s print|grep ' 2 '|awk '{print $2}'" % device)
        end = self.session.cmd_output(
            "parted -s %s unit s print|grep ' 2 '|awk '{print $3}'" % device)
        self.assertEqual(start, size + 's', "Start size is not correct")
        self.assertEqual(end, '4194270s', "End size is not correct")

    def test_cloudinit_provision_vm_with_multiple_nics(self):
        """
        :avocado: tags=tier2,cloudinit
        RHEL-176196	WALA-TC: [Cloudinit] Provision VM with multiple NICs
        1. Create a VM with 2 NICs
        2. Check if can provision and connect to the VM successfully
        """
        self.log.info(
            "RHEL-171393	WALA-TC: [Network] Provision VM with multiple NICs")
        self.vm.create()
        self.session.connect(timeout=60)
        vm_ip_list = self.session.cmd_output(
            "ip addr|grep -Po 'inet \\K.*(?=/)'|grep -v '127.0.0.1'").split(
                '\n').sort()
        azure_ip_list = self.vm.properties.get("privateIps").split(',').sort()
        self.assertEqual(
            vm_ip_list, azure_ip_list, "The private IP addresses are wrong.\n"
            "Expect: {}\nReal: {}".format(azure_ip_list, vm_ip_list))

    def test_cloudinit_provision_vm_with_sriov_nic(self):
        """
        :avocado: tags=tier2,cloudinit
        RHEL-171394	WALA-TC: [Network] Provision VM with SR-IOV NIC
        1. Create a VM with 1 SRIOV NIC
        2. Check if can provision and connect to the VM successfully
        """
        self.log.info(
            "RHEL-171394	WALA-TC: [Network] Provision VM with SR-IOV NIC")
        self.vm.create()
        self.session.connect(timeout=60)
        vm_ip = self.session.cmd_output(
            "ip addr|grep -Po 'inet \\K.*(?=/)'|grep -v '127.0.0.1'")
        azure_ip = self.vm.properties.get("privateIps")
        self.assertEqual(
            vm_ip, azure_ip, "The private IP addresses are wrong.\n"
            "Expect: {}\nReal: {}".format(azure_ip, vm_ip))

    def test_cloudinit_provision_vm_with_ipv6(self):
        """
        :avocado: tags=tier2,cloudinit
        RHEL-176199	WALA-TC: [Network] Provision VM with IPv6 address
        1. Create a VM with NIC in IPv6 subnet
        2. Check if can provision and connect to the VM successfully
        3. Restart the VM. Check if this NIC is up and can get ip address
        """
        self.log.info(
            "RHEL-176199 WALA-TC: [Network] Provision VM with IPv6 address")
        # 1. Create a VM with NIC in IPv6 subnet
        self.vm.create()
        self.session.connect(timeout=60)
        self.session.cmd_output("sudo su -")
        # 2. Verify can get IPv6 IP
        azure_ip = self.vm.properties.get("privateIps").split(',')[1]
        vm_ip = self.session.cmd_output(
            "ip addr|grep global|grep -Po 'inet6 \\K.*(?=/)'")
        self.assertEqual(
            vm_ip, azure_ip, "The private IPv6 address is wrong.\n"
            "Expect: {}\nReal: {}".format(azure_ip, vm_ip))
        self.assertEqual(0, self.session.cmd_status_output("ping6 ace:cab:deca::fe -c 1")[0],
                         "Cannot ping6 though vnet")
        # 3. Restart VM
        self.session.close()
        self.vm.reboot()
        time.sleep(10)
        self.session.connect(timeout=60)
        vm_ip_list = self.session.cmd_output(
            "ip addr|grep global|grep -Po 'inet6 \\K.*(?=/)'")
        self.assertEqual(
            vm_ip_list, azure_ip, "The private IPv6 address is wrong after restart.\n"
            "Expect: {}\nReal: {}".format(azure_ip, vm_ip_list))
        self.assertEqual(0, self.session.cmd_status_output("ping6 ace:cab:deca::fe -c 1")[0],
                         "Cannot ping6 though vnet after restart")

    def test_cloudinit_provision_gen2_vm(self):
        """
        :avocado: tags=tier2,cloudinit
        RHEL-178728	WALA-TC: [General] Verify provision Gen2 VM
        BZ#1714167
        """
        self.log.info(
            "RHEL-178728	WALA-TC: [General] Verify provision Gen2 VM")
        error_msg = ""
        # Verify hostname is correct
        try:
            self.assertEqual(self.session.cmd_output("hostname"), self.vm.vm_name,
                             "Hostname is not the one we set")
        except:
            error_msg += "Verify hostname failed\n"
        # Verify hostname is published to DNS
        try:
            self.assertIn(".internal.cloudapp.net",
                          self.session.cmd_output("hostname -f"),
                          "Cannot get whole FQDN")
            self.assertNotIn(
                "NXDOMAIN",
                self.session.cmd_output("nslookup {0}".format(
                    self.vm.vm_name)), "Fail to publish hostname to DNS")
        except:
            error_msg += "Verify publish to DNS failed\n"
        # Verify mountpoint
        try:
            self.assertEqual(
                0, self.session.cmd_status_output("mount|grep /mnt")[0],
                "Resource Disk is not mounted after provisioning")
        except:
            error_msg += "Verify mountpoint failed\n"
        if error_msg:
            self.fail(error_msg)

    def test_cloudinit_upgrade_downgrade_package(self):
        """
        :avocado: tags=tier2,cloudinit
        RHEL7-95122	WALA-TC: [Cloudinit] Upgrade cloud-init
        1. Downgrade through rpm
        2. Upgrade through rpm
        3. (if have repo)Downgrade through yum
        4. (if have repo)Upgrade through yum
        """
        self.log.info(
            "RHEL7-95122 WALA-TC: [Cloudinit] Upgrade cloud-init")
        self.session.cmd_output("sudo su -")
        self.assertEqual(0, self.session.cmd_status_output(
            "rpm -Uvh --oldpackage /tmp/{}".format(self.old_pkg))[0],
            "Fail to downgrade package through rpm")
        self.assertEqual(0, self.session.cmd_status_output(
            "rpm -Uvh /tmp/{}".format(self.package))[0],
            "Fail to upgrade package through rpm")
        self.assertNotIn("disabled", self.session.cmd_output("systemctl is-enabled cloud-init-local cloud-init cloud-config cloud-final"),
                         "After upgrade through rpm, the cloud-init services are not enabled")
        self.assertNotIn("inactive", self.session.cmd_output("systemctl is-active cloud-init-local cloud-init cloud-config cloud-final"),
                         "After upgrade through rpm, the cloud-init services are not active")
        self.assertEqual(0, self.session.cmd_status_output(
            "yum downgrade /tmp/{} -y --disablerepo=*".format(self.old_pkg))[0],
            "Fail to downgrade package through yum")
        self.assertEqual(0, self.session.cmd_status_output(
            "yum upgrade /tmp/{} -y --disablerepo=*".format(self.package))[0],
            "Fail to upgrade package through yum")
        self.assertNotIn("disabled", self.session.cmd_output("systemctl is-enabled cloud-init-local cloud-init cloud-config cloud-final"),
                         "After upgrade through yum, the cloud-init services are not enabled")
        self.assertNotIn("inactive", self.session.cmd_output("systemctl is-active cloud-init-local cloud-init cloud-config cloud-final"),
                         "After upgrade through yum, the cloud-init services are not active")
        self.session.cmd_output("rm -f /var/log/cloud-init*")
        self.session.close()
        self.vm.reboot()
        self.session.connect()
        try:
            self.test_cloudinit_check_cloudinit_log()
        except:
            self.log.warn("There are error/fail logs")

    def tearDown(self):
        if self.case_short_name == \
                "test_cloudinit_check_networkmanager_dispatcher":
            self.session.cmd_output("mv /tmp/enabled /run/cloud-init/")
            self.session.cmd_output("systemctl restart NetworkManager")
        elif self.case_short_name in [
                "test_cloudinit_provision_vm_with_multiple_nics",
                "test_cloudinit_provision_vm_with_sriov_nic",
                "test_cloudinit_provision_vm_with_ipv6",
                "test_cloudinit_provision_gen2_vm",
                "test_cloudinit_upgrade_downgrade_package"
        ]:
            self.vm.delete(wait=False)

    # def test_cloudinit_waagent_depro_user_with_cloudinit(self):
    #     """
    #     RHEL7-95001: WALA-TC: [Cloudinit] waagent -deprovision+user with
    #                  cloud-init enabled
    #     Description: waagent -deprovision+user should remove cloud-init
    #                  sudoers file. If not +user, should not remove this file
    #     1. Prepare a VM with wala and cloud-init installed. Enable
    #        cloud-init related services. Edit /etc/waagent.conf:
    #            Provisioning.Enabled=n
    #            Provisioning.UseCloudInit=y
    #        Deprovision this VM, shutdown, capture it as an image.
    #        Create a new VM base on this image.
    #     2. Check if /etc/sudoers.d/90-cloud-init-users exists
    #     3. Do not remove user account
    #        # waagent -deprovision -force
    #        Check if /etc/sudoers.d/90-cloud-init-users is not removed
    #     4. Remove the VM. Use the image to create a new one.
    #        Login. Remove user account
    #        # waagent -deprovision+user -force
    #        Check if /etc/sudoers.d/90-cloud-init-users is removed
    #     """
    #     self.log.info("waagent -deprovision+user with cloud-init enabled")
    #     self.log.info("Enable cloud-init related services. Edit /etc/\
    # waagent.conf. Deprovision, shutdown and capture.")
    #     self.session.cmd_output("systemctl enable cloud-{init-local,init,\
    # config,final}")
    #     time.sleep(1)
    #     self.assertNotIn("Disabled",
    #                      self.session.cmd_output("systemctl is-enabled \
    # cloud-{init-local,init,config,final}"),
    #                      "Fail to enable cloud-init related services")
    #     self.vm_test01.modify_value("Provisioning.Enabled", "n")
    #     self.vm_test01.modify_value("Provisioning.UseCloudInit", "y")
    #     self.session.cmd_output("waagent -deprovision+user -force")
    #     self.assertEqual(self.vm_test01.shutdown(), 0,
    #                      "Fail to shutdown VM")
    #     self.assertTrue(self.vm_test01.wait_for_deallocated(),
    #                     "VM status is not deallocated")
    #     cmd_params = {"os_state": "Generalized"}
    #     vm_image_name = self.vm_test01.name + "-cloudinit" + \
    #         self.vm_test01.postfix()
    #     self.assertEqual(self.vm_test01.capture(vm_image_name, cmd_params),
    #                      0,
    #                      "Fails to capture the vm: azure cli fail")
    #     self.assertTrue(self.vm_test01.wait_for_delete(check_cloudservice=False))
    #     new_vm_params = copy.deepcopy(self.vm_params)
    #     new_vm_params["Image"] = vm_image_name
    #     self.assertEqual(self.vm_test01.vm_create(new_vm_params), 0,
    #                      "Fail to create new VM base on the capture image: \
    # azure cli fail")
    #     self.assertTrue(self.vm_test01.wait_for_running() and \
    #         self.vm_test01.verify_alive(), "VM status is not running")
    #     self.log.info("2. Check if /etc/sudoers.d/90-cloud-init-users \
    # exists")
    #     self.assertTrue(self.vm_test01.is_file_exist("/etc/sudoers.d/90-cloud-init-users"),
    #                     "Fail to create /etc/sudoers.d/90-cloud-init-users")
    #     self.log.info("3. Do not remove user account")
    #     self.session.cmd_output("waagent -deprovision -force")
    #     # Login with root account because azure user account will be deleted
    #     self.assertTrue(self.vm_test01.verify_alive(username="root",
    #         password=self.vm_test01.password))

    # def test_cloudinit_upgrade_cloudinit(self):
    #     """
    #     RHEL7-95122: WALA-TC: [Cloudinit] Upgrade cloud-init
    #     1. Copy old cloud-init into VM. Get old and new cloud-init packages
    #     2. Remove new cloud-init. Install old cloud-init
    #     3. Upgrade to new cloud-init
    #     4. Deprovision. Use vhd to create a new VM. Check if works well
    #     """
    #     self.log.info("RHEL7-95122: WALA-TC: [Cloudinit] Upgrade cloud-init")
    #     # Login with root
    #     self.session.cmd_output("/usr/bin/cp -a /home/{0}/.ssh /root/;chown \
    # -R root:root /root/.ssh".format(self.vm_test01.username))
    #     self.vm_test01.session_close()
    #     self.vm_test01.verify_alive(username="root",
    #         authentication="publickey")
    #     # 1. Copy old cloud-init into VM
    #     ret = utils_misc.command(
    #         "ls %s/../tools/cloud-init-*.rpm" % REALPATH)
    #     self.assertEqual(0, ret.exit_status,
    #         "Fail to find old cloud-init package in host")
    #     old_pkg = os.path.basename(ret.stdout)
    #     self.vm_test01.copy_files_from(
    #         host_path="%s/../tools/%s" % (REALPATH, old_pkg),
    #         guest_path="/root/")
    #     self.assertTrue(self.vm_test01.is_file_exist("/root/"+old_pkg),
    #         "Cannot find %s in VM" % old_pkg)
    #     new_pkg = self.session.cmd_output("rpm -q cloud-init") + ".rpm"
    #     if not self.vm_test01.is_file_exist("/root/%s" % new_pkg):
    #         pattern=re.compile("cloud-init-(.*)-(\d+.el.*).(x86_64|noarch).rpm")
    #         res=pattern.search(new_pkg).groups()
    #         url="http://download-node-02.eng.bos.redhat.com/brewroot/packages/cloud-init/{0}/{1}/{2}/{3}"\
    #             .format(res[0],res[1],res[2],new_pkg)
    #         ret = utils_misc.command(
    #             "wget {0} -O /tmp/{1}".format(url, new_pkg)).exit_status
    #         self.assertEqual(0, ret,
    #             "Fail to download package from %s" % url)
    #         self.vm_test01.copy_files_from(host_path="/tmp/"+new_pkg,
    #                                        guest_path="/root/")
    #     self.assertTrue(self.vm_test01.is_file_exist("/root/"+new_pkg),
    #         "Cannot find %s in VM" % new_pkg)
    #     # 2. Remove new cloud-init. Install old cloud-init
    #     self.session.cmd_output("rpm -e cloud-init")
    #     self.session.cmd_output("rpm -ivh %s" % old_pkg)
    #     self.assertEqual(old_pkg, self.session.cmd_output(
    #         "rpm -q cloud-init")+".rpm",
    #         "%s is not installed successfully" % old_pkg)
    #     # 3. Upgrade to new cloud-init


if __name__ == "__main__":
    main()
