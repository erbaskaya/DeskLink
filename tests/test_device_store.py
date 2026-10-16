"""Persistent-device ID and saved-contacts regression tests."""
from pathlib import Path
import json
import tempfile
import unittest

from device_store import (
    get_or_create_identity, rotate_identity, put_server_url, get_server_url,
    save_contact, delete_contact, contacts, normalize_id,
)

URL = 'wss://desklink-relay.example.workers.dev/ws'
OTHER = 'wss://other.example.workers.dev/ws'


class DeviceStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.file = Path(self.tmp.name) / 'nested' / 'settings.json'

    def tearDown(self):
        self.tmp.cleanup()

    def test_identity_survives_restarts_and_does_not_change_on_server_update(self):
        first = get_or_create_identity(self.file)
        self.assertRegex(first[0], r'^[0-9]{9}$')
        self.assertRegex(first[1], r'^[0-9a-f]{64}$')
        self.assertEqual(first, get_or_create_identity(self.file))
        put_server_url(URL, self.file)
        self.assertEqual(first, get_or_create_identity(self.file))
        self.assertEqual(get_server_url('',self.file), URL)

    def test_device_key_recreated_only_if_conflicting_claim(self):
        a = get_or_create_identity(self.file)
        b = rotate_identity(self.file)
        self.assertNotEqual(a,b)
        self.assertEqual(get_or_create_identity(self.file),b)

    def test_saved_devices_are_reusable_and_separated_by_relay(self):
        get_or_create_identity(self.file)
        save_contact(URL,'123456789','Ofis Windows',connected=True,path=self.file)
        save_contact(URL,'987654321','MacBook',path=self.file)
        save_contact(OTHER,'123456789','Başka sistem',path=self.file)
        self.assertEqual([x['id'] for x in contacts(URL,self.file)], ['987654321','123456789'])
        save_contact(URL,'123456789','Ofis Windows 2',path=self.file)
        self.assertEqual(contacts(URL,self.file)[0]['name'],'Ofis Windows 2')
        self.assertTrue(contacts(URL,self.file)[0]['last_connected'])
        self.assertEqual(contacts(OTHER,self.file)[0]['name'],'Başka sistem')
        delete_contact(URL,'123456789',self.file)
        self.assertEqual(len(contacts(URL,self.file)),1)
        self.assertEqual(len(contacts(OTHER,self.file)),1)
        self.assertEqual(get_or_create_identity(self.file),get_or_create_identity(self.file))

    def test_settings_do_not_store_pin_or_contact_secret(self):
        get_or_create_identity(self.file)
        save_contact(URL, '123456789','Ofis PC', path=self.file)
        data=json.loads(self.file.read_text(encoding='utf-8'))
        self.assertNotIn('pin', data)
        self.assertNotIn('key', data['saved_devices'][0])
        self.assertIn('key',data['device_identity'])
        self.assertEqual(normalize_id('123 456 789'),'123456789')

    def test_invalid_ids_are_rejected(self):
        with self.assertRaises(ValueError):
            save_contact(URL,'abcdefgh1','Bad',path=self.file)
        with self.assertRaises(ValueError):
            save_contact(URL,'123','Bad',path=self.file)


if __name__ == '__main__':
    unittest.main()
