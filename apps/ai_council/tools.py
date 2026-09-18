from langchain_core.tools import tool

@tool()
def read_file(filename: str) -> str:
    """Read a file into a string"""
    with open(filename, "r", encoding='utf-8') as file:
        return file.read()

tools = [read_file]

