from neurahive.contracts import MCPProvider, ModelRequest, ModelResponse, ToolExecutor, VerificationResult, Verifier


def test_model_request_and_response_are_provider_neutral() -> None:
    request = ModelRequest(messages=[{"role": "user", "content": "hello"}])
    response = ModelResponse(content="hello")

    assert request.model_id is None
    assert response.content == "hello"


def test_verification_result_is_structured() -> None:
    result = VerificationResult(passed=True, reason="ok")
    assert result.passed is True
    assert result.reason == "ok"


def test_contracts_are_protocols() -> None:
    assert hasattr(Verifier, "verify")
    assert hasattr(ToolExecutor, "execute")
    assert hasattr(MCPProvider, "list_tools")
    assert hasattr(MCPProvider, "call_tool")
