import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from src import config, llm


class StructuredExtractionTests(unittest.IsolatedAsyncioTestCase):
    async def test_schema_uses_tool_input_instead_of_parsing_quoted_text(self):
        data = {"announcement_evidence": 'The founder said "we raised funding".'}
        response = SimpleNamespace(content=[SimpleNamespace(type="tool_use", name="return_json", input=data)])
        client = SimpleNamespace(messages=SimpleNamespace(create=AsyncMock(return_value=response)))
        schema = {"type":"object", "properties":{"announcement_evidence":{"type":"string"}}}
        with patch("anthropic.AsyncAnthropic", return_value=client):
            result = await llm.complete_json("Extract", "Article", schema=schema)
        self.assertEqual(result, data)
        self.assertEqual(client.messages.create.call_args.kwargs["tools"][0]["input_schema"], schema)
        self.assertEqual(client.messages.create.call_args.kwargs["tool_choice"], {"type":"tool", "name":"return_json"})

    async def test_missing_tool_result_is_not_silently_accepted(self):
        client = SimpleNamespace(messages=SimpleNamespace(create=AsyncMock(return_value=SimpleNamespace(content=[]))))
        with patch("anthropic.AsyncAnthropic", return_value=client):
            with self.assertRaises(ValueError):
                await llm.complete_json("Extract", "Article", schema={"type":"object"})

    async def test_client_is_reused_with_sdk_retries(self):
        response = SimpleNamespace(content=[SimpleNamespace(type="text", text='{"a": 1}')])
        client = SimpleNamespace(messages=SimpleNamespace(create=AsyncMock(return_value=response)))
        with patch("anthropic.AsyncAnthropic", return_value=client) as factory:
            await llm.complete_json("s", "u")
            await llm.complete_json("s", "u")
        factory.assert_called_once_with(max_retries=config.MODEL_MAX_RETRIES)

    def test_legacy_json_parser_is_preserved(self):
        self.assertEqual(llm._parse_json('```json\n{"answer":"yes"}\n```'), {"answer":"yes"})


if __name__ == "__main__":
    unittest.main()
