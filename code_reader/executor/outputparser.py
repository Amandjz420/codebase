from pydantic import BaseModel, Field
from typing import List

class CommandResponse(BaseModel):
    command: str = Field(description="The terminal command to be executed.")
    explanation: str = Field(description="Max 5-line explanation of why the command is needed.")

class Step(BaseModel):
    title: str = Field(description="summarizing the step in 1-2 lines")
    detailed_description: str = Field(description="=`detailed_description` with all necessary details.")
    psuedo_code: str = Field(description="`psuedo_code` field outlining the flow if code writing is involved.")
    code_snippet: str = Field(description="`code_snippet` field with a concrete code example if code writing is involved.")

class PlannerResponse(BaseModel):
    steps: List[Step] = Field(description="A list of detailed steps explaining what needs to be done without missing any details. "
                                          "If code is not relevant for a particular step, leave `psuedo_code` and `code_snippet` fields empty."
                                          "Make sure no essential details are missed. Provide a comprehensive, logically ordered plan.")

class CodeUpdateResponse(BaseModel):
    updated_code: str = Field(description="The updated or new code generated based on the feedback.")

class FeedbackResponse(BaseModel):
    feedback: str = Field(description="Feedback on whether the task was successfully executed or not.")

class FilepathResponse(BaseModel):
    files: List[str] = Field(description="list of file paths")

class SupervisorResponse(BaseModel):
    isChangeRequired: bool = Field(description="did user ask to change(or do something) in the project, or its code. ")
    aiReply: str = Field(description="response from the LLM for the instructions")
