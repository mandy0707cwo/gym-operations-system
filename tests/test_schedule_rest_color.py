from copy import deepcopy
import unittest
from scheduling import day_payload
from schedule_summary import summary_frame,colored_summary_frame
from test_schedule_headcounts import fixture,MONTH


class RestColorTests(unittest.TestCase):
    def test_colors_actual_regular_off_not_sunday_or_names_and_no_mutation(self):
        coaches,data=fixture()
        row=next(x for x in data['days'] if x['coach_id']=='a' and x['work_date']=='2026-10-01')
        row.update(day_payload('2026-10-01','regular_off'))
        coaches[0]['display_name']='例假'
        before=deepcopy(data)
        raw=summary_frame(coaches,data,MONTH,[])
        colored=colored_summary_frame(coaches,data,MONTH,[])
        self.assertIn(':blue-background[例假]',colored[('01','週四')].tolist())
        self.assertNotIn(':blue-background[A班]',colored[('04','週日')].tolist())
        self.assertIn('例假',colored[('教練','')].tolist())
        self.assertEqual(data,before)
        self.assertFalse(any(':blue-background[' in str(x) for x in raw.to_numpy().ravel()))
