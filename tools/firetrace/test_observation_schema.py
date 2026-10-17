import json
import unittest
from unittest.mock import patch
import main
from observation_schema import parse_observation


class ObservationTests(unittest.TestCase):
    def test_hidden_base_abstains_and_visible_coordinates_are_normalized(self):
        row={'smoke':True,'base_visible':False,'x_base':None,'y_base':None,'confidence':0.4,'reason':'Oculta por la cresta'}
        self.assertIsNone(parse_observation(json.dumps(row))['x_base'])
        with self.assertRaises(ValueError):parse_observation(json.dumps({k:v for k,v in row.items() if k!='x_base'}))
        for bad in [{'x_base':0.5},{'base_visible':True},{'confidence':True},{'smoke':'yes'}]:
            with self.assertRaises(ValueError):parse_observation(json.dumps({**row,**bad}))
        self.assertEqual(parse_observation(json.dumps({**row,'base_visible':True,'x_base':0.5,'y_base':0.7}))['y_base'],0.7)

    def test_proxy_forwards_task_and_rejects_old_unstructured_gateway(self):
        image='data:image/jpeg;base64,/9j/AA=='
        with patch.object(main,'BACKEND_PROXY','http://private'),patch.object(main,'remote',return_value=b'{"content":"old"}') as remote:
            with self.assertRaises(ValueError):main.analyze({'image':image,'task':'smoke-base-v1'})
            self.assertEqual(remote.call_args.args[1]['task'],'smoke-base-v1')

    def test_no_arbitrary_prompt_can_replace_the_fixed_task(self):
        with self.assertRaises(ValueError):main.analyze({'image':'data:image/jpeg;base64,/9j/AA==','task':'arbitrary'})

if __name__=='__main__':unittest.main()
