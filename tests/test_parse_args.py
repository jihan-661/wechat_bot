"""parse_args 的单元测试。

注意：选项采用"多 token 长值"语义——选项会一直吃到下一个选项开头，
因此选项的值可以含空格。这是提交 1673921「parse_args 支持长值」确立的行为。
"""
import unittest

from bot.command.base_command import parse_args


class TestParseArgs(unittest.TestCase):
    def test_option_consumes_long_value(self):
        # 选项吃到末尾：值可含空格
        self.assertEqual(parse_args(["-set", "a", "x"]), ({"set": "a x"}, []))

    def test_option_stops_at_next_option(self):
        self.assertEqual(
            parse_args(["-set", "a", "-other", "b"]),
            ({"set": "a", "other": "b"}, []),
        )

    def test_double_dash_is_normalized(self):
        # 回归：--key 曾被解析成 key="-key"
        self.assertEqual(parse_args(["--set", "prompt"]), ({"set": "prompt"}, []))

    def test_long_value_joined_by_space(self):
        self.assertEqual(
            parse_args(["-set", "prompt", "-value", "你是", "一个AI"]),
            ({"set": "prompt", "value": "你是 一个AI"}, []),
        )

    def test_boolean_switch(self):
        self.assertEqual(parse_args(["-v"]), ({"v": ""}, []))

    def test_positional_before_option(self):
        self.assertEqual(parse_args(["config", "-set", "k"]), ({"set": "k"}, ["config"]))

    def test_negative_int_is_positional(self):
        # 回归：-1 曾被当作 key="1" 的选项
        self.assertEqual(parse_args(["-1"]), ({}, ["-1"]))

    def test_negative_float_is_positional(self):
        self.assertEqual(parse_args(["-3.5"]), ({}, ["-3.5"]))

    def test_bare_dash_is_positional(self):
        self.assertEqual(parse_args(["-"]), ({}, ["-"]))

    def test_bare_double_dash_is_positional(self):
        self.assertEqual(parse_args(["--"]), ({}, ["--"]))

    def test_empty_tokens(self):
        self.assertEqual(parse_args([]), ({}, []))

    def test_two_double_dash_options(self):
        self.assertEqual(
            parse_args(["--set", "model", "--value", "gpt-4o"]),
            ({"set": "model", "value": "gpt-4o"}, []),
        )


if __name__ == "__main__":
    unittest.main()
