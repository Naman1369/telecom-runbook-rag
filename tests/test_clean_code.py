import pytest
from app.ingest.cleaning import clean_text


@pytest.mark.parametrize("fence", ["```", "~~~"])
def test_cleaning_preserves_command_arguments_and_comments(fence):
    text = f'Home | Docs\n{fence}\nset description "two  spaces"\n# log in before running\n{fence}\nNormal   prose'
    expected = f'\n{fence}\nset description "two  spaces"\n# log in before running\n{fence}\nNormal prose'
    assert clean_text(text) == expected
    assert len(clean_text(text).splitlines()) == len(text.splitlines())
