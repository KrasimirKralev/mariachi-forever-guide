import unittest

from forever import luatable as lt

# A snippet in the game's own saved-variables syntax: CRLF line ends, ["key"] = value, "-- [n]" after array items,
# escaped quotes and backslashes, a "\n" inside a string, nested tables, a sparse table with number keys.
SNIPPET = (
    '\r\nForeverBridgeDB = {\r\n["schema"] = 1,\r\n["auto"] = false,\r\n["chars"] = {\r\n["Testa-Mockrealm"] = {\r\n'
    '["name"] = "Te\\"sta",\r\n["note"] = "line one\\nline two \\\\ end",\r\n["money"] = -15,\r\n["ratio"] = 0.25,\r\n'
    '["equipped"] = {\r\n{\r\n["slot"] = "Head",\r\n["id"] = 900001,\r\n}, -- [1]\r\n{\r\n["slot"] = "Neck",\r\n'
    '}, -- [2]\r\n},\r\n["bags"] = {\r\n[920001] = 20,\r\n[900010] = 1,\r\n},\r\n},\r\n},\r\n}\r\nOtherAddonDB = nil\r\n'
)


class SavedVariables(unittest.TestCase):
    def test_real_syntax_snippet(self):
        data = lt.parse(SNIPPET)
        db = data['ForeverBridgeDB']
        c = db['chars']['Testa-Mockrealm']
        self.assertEqual(db['schema'], 1)
        self.assertIs(db['auto'], False)
        self.assertEqual(c['name'], 'Te"sta')
        self.assertEqual(c['note'], 'line one\nline two \\ end')
        self.assertEqual(c['money'], -15)
        self.assertEqual(c['ratio'], 0.25)
        self.assertEqual([e['slot'] for e in c['equipped']], ['Head', 'Neck'])
        self.assertEqual(c['bags'], {920001: 20, 900010: 1})
        self.assertIsNone(data['OtherAddonDB'])

    def test_values(self):
        d = lt.parse('A = { 1, 2.5, -3, 0x1F, 1e3, true, false, nil, "x", \'y\', [[long\nstring]], k = "v" }')['A']
        self.assertEqual(d[1], 1)
        self.assertEqual(d[2], 2.5)
        self.assertEqual(d[3], -3)
        self.assertEqual(d[4], 31)
        self.assertEqual(d[5], 1000.0)
        self.assertIs(d[6], True)
        self.assertIs(d[7], False)
        self.assertIsNone(d[8])
        self.assertEqual(d[9], 'x')
        self.assertEqual(d[10], 'y')
        self.assertEqual(d[11], 'long\nstring')
        self.assertEqual(d['k'], 'v')

    def test_decimal_escapes_keep_bytes(self):
        self.assertEqual(lt.parse(r'A = "\65\066\9"')['A'], 'AB\t')

    def test_comments_are_skipped(self):
        self.assertEqual(lt.parse('-- a comment\nA = { --[[ block\n comment ]] 1, -- [1]\n}')['A'], [1])

    def test_empty_table_is_a_list(self):
        self.assertEqual(lt.parse('A = {}')['A'], [])

    def test_broken_input_raises(self):
        for bad in ('A = { 1, 2', 'A = { ["k"] 1 }', 'A = { @ }', 'A = -"x"'):
            with self.assertRaises(lt.LuaError):
                lt.parse(bad)

    def test_never_runs_code(self):
        # a function call is not data: it is refused, nothing is executed
        with self.assertRaises(lt.LuaError):
            lt.parse('A = { os.execute("x") }')

    def test_D_and_L(self):
        self.assertEqual(lt.D([1]), {})
        self.assertEqual(lt.L({2: 'b', 1: 'a', 'x': 'z'}), ['a', 'b'])
        self.assertEqual(lt.L(None), [])


class ForeverDBText(unittest.TestCase):
    TEXT = ('local _, ns = ...\nns.a = {\n[1]="one|two",\n[22]="say \\"hi\\" {not a brace}",\n}\n'
            'ns.b = {[5]={s="4jr6bq1",o={[1]="x"}},[6]={"Name","Title",9901,12.3,45.6,"H",1}}\n')

    def test_section_handles_braces_inside_strings(self):
        body = lt.section(self.TEXT, 'a')
        self.assertIn('{not a brace}', body)
        self.assertNotIn('ns.b', body)
        self.assertEqual(lt.section(self.TEXT, 'missing'), '')

    def test_maps(self):
        self.assertEqual(lt.str_map(self.TEXT, 'a'), {1: 'one|two', 22: 'say "hi" {not a brace}'})
        t = lt.tbl_map(self.TEXT, 'b')
        self.assertIn('s="4jr6bq1"', t[5])
        self.assertEqual(lt.fields(t[6]), ['Name', 'Title', 9901, 12.3, 45.6, 'H', 1])

    def test_spots_and_base36(self):
        self.assertEqual(lt.decode_spot('4jr6bq1'), (9901, 63.1, 44.9))
        self.assertIsNone(lt.decode_spot('not-base-36!'))
        self.assertEqual(lt.spots('4jr6bq1 !! 4jroyac'), [(9901, 63.1, 44.9), (9902, 50.0, 50.0)])
        self.assertEqual(lt.b36(900001), 'jag1')
        self.assertEqual(lt.b36(0), '0')


if __name__ == '__main__':
    unittest.main()
