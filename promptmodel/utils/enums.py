from enum import Enum

class LocalTask(str, Enum):
    RUN_LLM_MODULE = "RUN_LLM_MODULE"
    EVAL_LLM_MODULE = "EVAL_LLM_MODULE"
    LIST_MODULES = "LIST_MODULES"
    LIST_VERSIONS = "LIST_VERSIONS"
    LIST_SAMPLES = "LIST_SAMPLES"
    GET_PROMPTS = "GET_PROMPTS"
    GET_RUN_LOGS = "GET_RUN_LOGS"
    CHANGE_VERSION_STATUS = "CHANGE_VERSION_STATUS"
    GET_VERSION_TO_SAVE = "GET_VERSION_TO_SAVE"
    GET_VERSIONS_TO_SAVE = "GET_VERSIONS_TO_SAVE"
    UPDATE_CANDIDATE_VERSION_ID = "UPDATE_CANDIDATE_VERSION_ID"

class ServerTask(str, Enum):
    UPDATE_RESULT_RUN = "UPDATE_RESULT_RUN"
    LOCAL_UPDATE_ALERT = "LOCAL_UPDATE_ALERT"
    UPDATE_RESULT_EVAL = "UPDATE_RESULT_EVAL"
    
class LLMModuleVersionStatus(Enum):
    BROKEN = "broken"
    WORKING = "working"
    CANDIDATE = "candidate"
    
class ChangeLogAction(str, Enum):
    ADD: str = "ADD"
    DELETE: str = "DEL"
    CHANGE: str = "CHG"
    FIX: str = "FIX"

class Role(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    
class ParsingType(str, Enum):
    COLON = "colon" 
    SQUARE_BRACKET = "square_bracket"
    DOUBLE_SQUARE_BRACKET = "double_square_bracket"
    HTML = "html"
    
class ParsingPattern(dict, Enum):
    COLON = {
        "start" : r"(.*?): \n",
        "start_fstring": "{key}: \n",
        "end_fstring": None,
        "whole": r"(.*?): (.*?)\n",
        "start_token" : None,
        "end_token" : None
    }
    SQUARE_BRACKET = {
        "start" : r"\[(.*?)\]",
        "start_fstring": "[{key}]",
        "end_fstring": "[/{key}]",
        "whole": r"\[(.*?)\](.*?)\[/\1\]",
        "start_token" : r"[",
        "end_token" : r"]"
    }
    DOUBLE_SQUARE_BRACKET = {
        "start" : r"\[\[(.*?)\]\]",
        "start_fstring": "[[{key}]]",
        "end_fstring" : "[[/{key}]]",
        "whole" : r"\[\[(.*?)\]\](.*?)\[\[/\1\]\]",
        "start_token" : r"[",
        "end_token" : r"]"
    }
    HTML = {
        "start" : r"<(.*?)>",
        "start_fstring": "<{key}>",
        "end_fstring": "</{key}>",
        "whole" : r"<(.*?)>(.*?)</\1>",
        "start_token" : r"<",
        "end_token" : r">"
    }

def get_pattern_by_type(parsing_type_value):
    return ParsingPattern[ParsingType(parsing_type_value).name].value
