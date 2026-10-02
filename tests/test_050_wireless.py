import copy
import unittest
from pydantic import ValidationError
from mcp_hcl.planning import TopologyRequest, WirelessSettings, plan_topology, estimate_plan
from mcp_hcl.services import Wireless
from mcp_hcl.topology import validate_plan
from mcp_hcl.generation import generate_configs,generate_operations,render_wireless


class ProfileCatalog:
    def devices(self):
        def cli(model):return {'model':model,'default_interfaces':[f'GigabitEthernet0/{n}' for n in range(8)],'evidence':{'source':'synthetic-test-only','sha256':'0'*64}}
        return {'devices':[cli(n) for n in ('MSR36-20','S5820V2-54QS-GE','AC','AP')]+[
            {'model':'Phone','control_kind':'native_gui','default_interfaces':[],'native_interfaces':['WLAN-Radio_0/1'],
             'capabilities':{'ipv4_modes':['dhcp'],'ipv6_modes':['none'],'wireless_security':['open']},
             'evidence':{'source':'synthetic-test-only','sha256':'0'*64}}]}


def request():
    return {'template':'single_lan','wireless_clients_per_lan':2,'wireless_client_model':'Phone',
            'access_points':1,'ap_model':'AP','ac_model':'AC','dhcp':True,
            'wireless_settings':{'security':'open','ssid':'diagnostic','hardware_model':'WA6320-HCL','serial_ids':['observed_serial']}}


class Wireless050Tests(unittest.TestCase):
    def test_security_is_explicit_no_key_leak_or_downgrade(self):
        base={'ssid':'lab','hardware_model':'observed','serial_ids':['actual']}
        with self.assertRaises(ValidationError): WirelessSettings.model_validate(base)
        for fields in ({'security':'open','psk':'testpass12'},{'security':'wpa2_psk'}):
            with self.assertRaises(ValidationError): WirelessSettings.model_validate(base|fields)
        self.assertEqual(WirelessSettings.model_validate(base|{'psk':'testpass12'}).security,'wpa2_psk')
        secure=request();secure['wireless_settings'].update(security='wpa2_psk',psk='testpass12')
        result=plan_topology(secure,ProfileCatalog())
        self.assertEqual(result['errors'][0]['code'],'wireless_security_unverified')
        self.assertNotIn('testpass12',str(result))

    def test_phone_open_intent_dhcp_vlan_and_manifest_are_not_generation_success(self):
        catalog=ProfileCatalog();result=plan_topology(request(),catalog)
        self.assertTrue(result['valid'],result.get('errors'))
        plan=result['plan'];phones={d['id'] for d in plan['devices'] if d['model']=='Phone'}
        self.assertEqual(len(phones),2)
        self.assertFalse(any(a['device'] in phones for a in plan['addresses']))
        self.assertTrue(all(h['ipv4']=='dhcp' and h['ipv6']=='none' for h in plan['host_settings'] if h['device'] in phones))
        self.assertEqual(estimate_plan(request(),catalog)['estimate']['devices'],len(plan['devices']))
        self.assertEqual(generate_configs(plan,catalog)['status'],'rejected')
        operations=generate_operations(plan,catalog,False)
        self.assertFalse(operations['executable'])
        self.assertEqual(len([o for o in operations['operations'] if o['action']=='associate_wireless_terminal']),2)

    def test_phone_modes_and_security_dependencies_reject_invalid_custom_plans(self):
        catalog=ProfileCatalog();plan=plan_topology(request(),catalog)['plan']
        for change in ('static','slaac','security','ssid','service','svi_pool'):
            altered=copy.deepcopy(plan);phone=next(d['id'] for d in plan['devices'] if d['model']=='Phone')
            host=next(h for h in altered['host_settings'] if h['device']==phone)
            if change=='static':host['ipv4']='static'
            if change=='slaac':host['ipv6']='slaac'
            if change=='security':altered['wireless_associations'][0]['security']='wpa2_psk'
            if change=='ssid':altered['wireless_associations'][0]['ssid']='wrong'
            if change=='service':altered['services'].append({'device':phone,'feature':'vlan','parameters':{'vlans':[10]}})
            if change=='svi_pool':
                for service in altered['services']:
                    if service['feature']=='dhcp':service['parameters']['excluded']=service['parameters']['excluded'][:1]
            self.assertFalse(validate_plan(altered,catalog)['valid'],change)

    def test_overlapping_groups_dualstack_and_unknown_fields_rejected(self):
        for fields in ({'wireless_laptops':True,'laptops_per_lan':2,'laptop_model':'Phone'}, {'dual_stack':True}, {'wireless_clients_per_lan':True}, {'typo':1}):
            with self.assertRaises(ValidationError):TopologyRequest.model_validate(request()|fields)

    def test_open_and_secure_controller_templates_preserve_security_intent(self):
        params={'mode':'ac','template':'test','ssid':'lab','vlan':10,'ap_device':'ap1','ap_name':'ap1','ap_model':'observed','serial_id':'actual'}
        opened=render_wireless(Wireless.model_validate(params|{'security':'open'}))
        self.assertFalse(any('psk' in line or 'preshared' in line for line in opened))
        secured=render_wireless(Wireless.model_validate(params|{'psk':'testpass12'}))
        self.assertIn('akm mode psk',secured)
