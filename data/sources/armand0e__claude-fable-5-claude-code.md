---
pretty_name: claude-fable-5 Agent Traces
task_categories:
- text-generation
tags:
- agent-traces
- format:agent-traces
- claude
- distillation
- claude-fable-5
- teich
configs:
- config_name: default
  data_files:
  - split: train
    path: '*.jsonl'
license: mit
---

# claude-fable-5 Agent Traces

It's worth noting that our team was working with [**Glint-Research**](https://huggingface.co/datasets/Glint-Research) to collect as much fable data as possible.

These are just the anonymized raw traces of both of our teams combined. This means that [Glint-Research/Fable-5-traces](https://huggingface.co/datasets/Glint-Research/Fable-5-traces) was created from formatting and splitting up this same dataset. If you use one for your tune, don't use the other (it's the same exact data).

---

For training on this dataset I recommend using the teich package to convert to openai style chats. It parses and filters out things like hitting limits and model switches, etc. As well as knows the exact tool-schemas and descriptions for the tools used.

I encourage everyone to please upload their fable-5 traces from whatever harness they may have used. This is all valuable data and we need to pool it together to make something meaningful :)

To easily extract and anonymize your data you can use teich as well:

```bash
pip install -U teich
```

```bash
teich extract claude --model fable-5
# teich extract hermes --model fable-5
# teich extract pi --model fable-5
# teich extract cursor --model fable-5
```

Check out teich on github for more info about all that the package can do! 

https://github.com/TeichAI/teich

## Tool schema snapshot

<details>
<summary>Training-ready tool schema snapshot</summary>

```json
[
  {
    "type": "function",
    "function": {
      "name": "Agent",
      "description": "Call the Claude deferred tool Agent.",
      "parameters": {
        "type": "object",
        "properties": {
          "description": {
            "type": "string"
          },
          "prompt": {
            "type": "string"
          },
          "run_in_background": {
            "type": "boolean"
          },
          "subagent_type": {
            "type": "string"
          }
        },
        "additionalProperties": true,
        "required": [
          "description",
          "prompt",
          "run_in_background"
        ]
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "AskUserQuestion",
      "description": "Call the Claude deferred tool AskUserQuestion.",
      "parameters": {
        "type": "object",
        "properties": {
          "questions": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "header": {
                  "type": "string"
                },
                "multiSelect": {
                  "type": "boolean"
                },
                "options": {
                  "type": "array",
                  "items": {
                    "type": "object",
                    "properties": {
                      "description": {
                        "type": "string"
                      },
                      "label": {
                        "type": "string"
                      }
                    },
                    "additionalProperties": true,
                    "required": [
                      "description",
                      "label"
                    ]
                  }
                },
                "question": {
                  "type": "string"
                }
              },
              "additionalProperties": true,
              "required": [
                "header",
                "multiSelect",
                "options",
                "question"
              ]
            }
          }
        },
        "additionalProperties": true,
        "required": [
          "questions"
        ]
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "Bash",
      "description": "Run a shell command.",
      "parameters": {
        "type": "object",
        "properties": {
          "command": {
            "type": "string"
          },
          "description": {
            "type": "string"
          },
          "run_in_background": {
            "type": "boolean"
          },
          "timeout": {
            "type": "integer"
          }
        },
        "additionalProperties": true,
        "required": [
          "command"
        ]
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "BashOutput",
      "description": "Read output from a running background shell command.",
      "parameters": {
        "type": "object",
        "properties": {
          "bash_id": {
            "type": "string"
          },
          "filter": {
            "type": "string"
          }
        },
        "additionalProperties": true,
        "required": [
          "bash_id"
        ]
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "CronCreate",
      "description": "Create a scheduled Claude Desktop task.",
      "parameters": {
        "type": "object",
        "properties": {
          "name": {
            "type": "string"
          },
          "prompt": {
            "type": "string"
          },
          "schedule": {
            "type": "string"
          },
          "timezone": {
            "type": "string"
          }
        },
        "additionalProperties": true
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "CronDelete",
      "description": "Delete a scheduled Claude Desktop task.",
      "parameters": {
        "type": "object",
        "properties": {
          "cronId": {
            "type": "string"
          },
          "name": {
            "type": "string"
          }
        },
        "additionalProperties": true
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "CronList",
      "description": "List scheduled Claude Desktop tasks.",
      "parameters": {
        "type": "object",
        "properties": {},
        "additionalProperties": true
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "DesignSync",
      "description": "Synchronize design context from Claude Desktop.",
      "parameters": {
        "type": "object",
        "properties": {
          "target": {
            "type": "string"
          }
        },
        "additionalProperties": true
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "Edit",
      "description": "Replace text in an existing file.",
      "parameters": {
        "type": "object",
        "properties": {
          "file_path": {
            "type": "string"
          },
          "new_string": {
            "type": "string"
          },
          "old_string": {
            "type": "string"
          },
          "replace_all": {
            "type": "boolean"
          }
        },
        "additionalProperties": true,
        "required": [
          "file_path",
          "new_string",
          "old_string"
        ]
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "EnterPlanMode",
      "description": "Enter Claude Desktop plan mode.",
      "parameters": {
        "type": "object",
        "properties": {
          "prompt": {
            "type": "string"
          }
        },
        "additionalProperties": true
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "EnterWorktree",
      "description": "Enter a Claude Desktop worktree.",
      "parameters": {
        "type": "object",
        "properties": {
          "branch": {
            "type": "string"
          },
          "path": {
            "type": "string"
          }
        },
        "additionalProperties": true
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "ExitPlanMode",
      "description": "Exit Claude Desktop plan mode.",
      "parameters": {
        "type": "object",
        "properties": {
          "plan": {
            "type": "string"
          }
        },
        "additionalProperties": true
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "ExitWorktree",
      "description": "Exit the active Claude Desktop worktree.",
      "parameters": {
        "type": "object",
        "properties": {},
        "additionalProperties": true
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "Glob",
      "description": "Find files by glob pattern.",
      "parameters": {
        "type": "object",
        "properties": {
          "path": {
            "type": "string"
          },
          "pattern": {
            "type": "string"
          }
        },
        "additionalProperties": true,
        "required": [
          "pattern"
        ]
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "Grep",
      "description": "Search file contents by pattern.",
      "parameters": {
        "type": "object",
        "properties": {
          "-A": {
            "type": "integer"
          },
          "-B": {
            "type": "integer"
          },
          "-C": {
            "type": "integer"
          },
          "head_limit": {
            "type": "integer"
          },
          "include": {
            "type": "string"
          },
          "output_mode": {
            "type": "string"
          },
          "path": {
            "type": "string"
          },
          "pattern": {
            "type": "string"
          }
        },
        "additionalProperties": true,
        "required": [
          "pattern"
        ]
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "KillBash",
      "description": "Stop a running background shell command.",
      "parameters": {
        "type": "object",
        "properties": {
          "shell_id": {
            "type": "string"
          }
        },
        "additionalProperties": true,
        "required": [
          "shell_id"
        ]
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "LS",
      "description": "List files and directories.",
      "parameters": {
        "type": "object",
        "properties": {
          "ignore": {
            "type": "array",
            "items": {
              "type": "string"
            }
          },
          "path": {
            "type": "string"
          }
        },
        "additionalProperties": true,
        "required": [
          "path"
        ]
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "ListMcpResourcesTool",
      "description": "Call the Claude deferred tool ListMcpResourcesTool.",
      "parameters": {
        "type": "object",
        "properties": {},
        "additionalProperties": true
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "Monitor",
      "description": "Monitor a long-running Claude Desktop task.",
      "parameters": {
        "type": "object",
        "properties": {
          "interval": {
            "type": "string"
          },
          "taskId": {
            "type": "string"
          }
        },
        "additionalProperties": true
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "MultiEdit",
      "description": "Apply multiple text replacements to one file.",
      "parameters": {
        "type": "object",
        "properties": {
          "edits": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "old_string": {
                  "type": "string"
                },
                "new_string": {
                  "type": "string"
                },
                "replace_all": {
                  "type": "boolean"
                }
              },
              "required": [
                "old_string",
                "new_string"
              ],
              "additionalProperties": true
            }
          },
          "file_path": {
            "type": "string"
          }
        },
        "additionalProperties": true,
        "required": [
          "edits",
          "file_path"
        ]
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "NotebookEdit",
      "description": "Edit a Jupyter notebook cell.",
      "parameters": {
        "type": "object",
        "properties": {
          "cell_id": {
            "type": "string"
          },
          "cell_type": {
            "type": "string"
          },
          "edit_mode": {
            "type": "string"
          },
          "new_source": {
            "type": "string"
          },
          "notebook_path": {
            "type": "string"
          }
        },
        "additionalProperties": true,
        "required": [
          "new_source",
          "notebook_path"
        ]
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "NotebookRead",
      "description": "Read a Jupyter notebook.",
      "parameters": {
        "type": "object",
        "properties": {
          "notebook_path": {
            "type": "string"
          }
        },
        "additionalProperties": true,
        "required": [
          "notebook_path"
        ]
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "PushNotification",
      "description": "Send a Claude Desktop push notification.",
      "parameters": {
        "type": "object",
        "properties": {
          "message": {
            "type": "string"
          },
          "title": {
            "type": "string"
          }
        },
        "additionalProperties": true
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "Read",
      "description": "Read a file.",
      "parameters": {
        "type": "object",
        "properties": {
          "file_path": {
            "type": "string"
          },
          "limit": {
            "type": "integer"
          },
          "offset": {
            "type": "integer"
          }
        },
        "additionalProperties": true,
        "required": [
          "file_path"
        ]
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "ReadMcpResourceTool",
      "description": "Call the Claude deferred tool ReadMcpResourceTool.",
      "parameters": {
        "type": "object",
        "properties": {},
        "additionalProperties": true
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "RemoteTrigger",
      "description": "Trigger a remote Claude Desktop action.",
      "parameters": {
        "type": "object",
        "properties": {
          "prompt": {
            "type": "string"
          },
          "target": {
            "type": "string"
          }
        },
        "additionalProperties": true
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "ScheduleWakeup",
      "description": "Call the Claude deferred tool ScheduleWakeup.",
      "parameters": {
        "type": "object",
        "properties": {
          "delaySeconds": {
            "type": "integer"
          },
          "prompt": {
            "type": "string"
          },
          "reason": {
            "type": "string"
          }
        },
        "additionalProperties": true,
        "required": [
          "delaySeconds",
          "prompt",
          "reason"
        ]
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "SendUserFile",
      "description": "Call the Claude deferred tool SendUserFile.",
      "parameters": {
        "type": "object",
        "properties": {
          "caption": {
            "type": "string"
          },
          "files": {
            "type": "array",
            "items": {
              "type": "string"
            }
          },
          "status": {
            "type": "string"
          }
        },
        "additionalProperties": true,
        "required": [
          "caption",
          "files",
          "status"
        ]
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "Skill",
      "description": "Load and use a Claude Desktop skill.",
      "parameters": {
        "type": "object",
        "properties": {
          "args": {
            "type": "string"
          },
          "skill": {
            "type": "string"
          }
        },
        "additionalProperties": true,
        "required": [
          "skill"
        ]
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "StructuredOutput",
      "description": "Call the Claude deferred tool StructuredOutput.",
      "parameters": {
        "type": "object",
        "properties": {
          "findings": {
            "anyOf": [
              {
                "anyOf": [
                  {
                    "anyOf": [
                      {
                        "anyOf": [
                          {
                            "type": "array",
                            "items": {
                              "type": "object",
                              "properties": {
                                "detail": {
                                  "type": "string"
                                },
                                "effort": {
                                  "type": "string"
                                },
                                "expected role": {
                                  "type": "null"
                                },
                                "expected_gain": {
                                  "type": "string"
                                },
                                "risk": {
                                  "type": "string"
                                },
                                "title": {
                                  "type": "string"
                                }
                              },
                              "additionalProperties": true,
                              "required": [
                                "detail",
                                "effort",
                                "expected_gain",
                                "risk",
                                "title"
                              ]
                            }
                          },
                          {
                            "type": "array",
                            "items": {
                              "type": "object",
                              "properties": {
                                "detail": {
                                  "type": "string"
                                },
                                "effort": {
                                  "type": "string"
                                },
                                "expected_gain": {
                                  "type": "string"
                                },
                                "risk": {
                                  "type": "string"
                                },
                                "title": {
                                  "type": "string"
                                }
                              },
                              "additionalProperties": true,
                              "required": [
                                "detail",
                                "expected_gain",
                                "risk",
                                "title"
                              ]
                            }
                          }
                        ]
                      },
                      {
                        "type": "array",
                        "items": {
                          "type": "object",
                          "properties": {
                            "detail": {
                              "type": "string"
                            },
                            "effort": {
                              "type": "string"
                            },
                            "expected_gain": {
                              "type": "string"
                            },
                            "risk": {
                              "type": "string"
                            },
                            "title": {
                              "type": "string"
                            }
                          },
                          "additionalProperties": true,
                          "required": [
                            "detail",
                            "effort",
                            "expected_gain",
                            "risk",
                            "title"
                          ]
                        }
                      }
                    ]
                  },
                  {
                    "type": "array",
                    "items": {
                      "type": "object",
                      "properties": {
                        "detail": {
                          "type": "string"
                        },
                        "effort": {
                          "type": "string"
                        },
                        "expected_gain": {
                          "type": "string"
                        },
                        "risk": {
                          "type": "string"
                        },
                        "title": {
                          "type": "string"
                        }
                      },
                      "additionalProperties": true,
                      "required": [
                        "detail",
                        "effort",
                        "expected_gain",
                        "risk",
                        "title"
                      ]
                    }
                  }
                ]
              },
              {
                "type": "array",
                "items": {
                  "type": "object",
                  "properties": {
                    "detail": {
                      "type": "string"
                    },
                    "effort": {
                      "type": "string"
                    },
                    "expected_gain": {
                      "type": "string"
                    },
                    "risk": {
                      "type": "string"
                    },
                    "title": {
                      "type": "string"
                    }
                  },
                  "additionalProperties": true,
                  "required": [
                    "detail",
                    "effort",
                    "expected_gain",
                    "risk",
                    "title"
                  ]
                }
              }
            ]
          }
        },
        "additionalProperties": true,
        "required": [
          "findings"
        ]
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "Task",
      "description": "Launch a subagent to complete a delegated task.",
      "parameters": {
        "type": "object",
        "properties": {
          "description": {
            "type": "string"
          },
          "prompt": {
            "type": "string"
          },
          "subagent_type": {
            "type": "string"
          }
        },
        "additionalProperties": true,
        "required": [
          "prompt"
        ]
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "TaskCreate",
      "description": "Create a tracked task in the Claude Desktop task list.",
      "parameters": {
        "type": "object",
        "properties": {
          "activeForm": {
            "type": "string"
          },
          "description": {
            "type": "string"
          },
          "subject": {
            "type": "string"
          }
        },
        "additionalProperties": true,
        "required": [
          "activeForm",
          "description",
          "subject"
        ]
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "TaskGet",
      "description": "Fetch one tracked Claude Desktop task.",
      "parameters": {
        "type": "object",
        "properties": {
          "taskId": {
            "type": "string"
          }
        },
        "additionalProperties": true,
        "required": [
          "taskId"
        ]
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "TaskList",
      "description": "List tracked Claude Desktop tasks.",
      "parameters": {
        "type": "object",
        "properties": {
          "includeCompleted": {
            "type": "boolean"
          },
          "status": {
            "type": "string"
          }
        },
        "additionalProperties": true
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "TaskOutput",
      "description": "Read output associated with a tracked Claude Desktop task.",
      "parameters": {
        "type": "object",
        "properties": {
          "lines": {
            "type": "integer"
          },
          "taskId": {
            "type": "string"
          }
        },
        "additionalProperties": true,
        "required": [
          "taskId"
        ]
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "TaskStop",
      "description": "Stop a tracked Claude Desktop task.",
      "parameters": {
        "type": "object",
        "properties": {
          "taskId": {
            "type": "string"
          }
        },
        "additionalProperties": true,
        "required": [
          "taskId"
        ]
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "TaskUpdate",
      "description": "Update the status of a tracked Claude Desktop task.",
      "parameters": {
        "type": "object",
        "properties": {
          "status": {
            "type": "string"
          },
          "taskId": {
            "type": "string"
          }
        },
        "additionalProperties": true,
        "required": [
          "status",
          "taskId"
        ]
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "TodoWrite",
      "description": "Create or update the task list.",
      "parameters": {
        "type": "object",
        "properties": {
          "todos": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "content": {
                  "type": "string"
                },
                "status": {
                  "type": "string"
                },
                "priority": {
                  "type": "string"
                },
                "id": {
                  "type": "string"
                }
              },
              "required": [
                "content",
                "status",
                "priority",
                "id"
              ],
              "additionalProperties": true
            }
          }
        },
        "additionalProperties": true,
        "required": [
          "todos"
        ]
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "ToolSearch",
      "description": "Load deferred Claude Desktop or MCP tools by search query.",
      "parameters": {
        "type": "object",
        "properties": {
          "max_results": {
            "type": "integer"
          },
          "query": {
            "type": "string"
          }
        },
        "additionalProperties": true,
        "required": [
          "query"
        ]
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "WebFetch",
      "description": "Fetch web content from a URL.",
      "parameters": {
        "type": "object",
        "properties": {
          "prompt": {
            "type": "string"
          },
          "url": {
            "type": "string"
          }
        },
        "additionalProperties": true,
        "required": [
          "prompt",
          "url"
        ]
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "WebSearch",
      "description": "Search the web.",
      "parameters": {
        "type": "object",
        "properties": {
          "allowed_domains": {
            "type": "array",
            "items": {
              "type": "string"
            }
          },
          "blocked_domains": {
            "type": "array",
            "items": {
              "type": "string"
            }
          },
          "query": {
            "type": "string"
          }
        },
        "additionalProperties": true,
        "required": [
          "query"
        ]
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "Workflow",
      "description": "Call the Claude deferred tool Workflow.",
      "parameters": {
        "type": "object",
        "properties": {
          "script": {
            "type": "string"
          },
          "scriptPath": {
            "type": "string"
          }
        },
        "additionalProperties": true
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "Write",
      "description": "Write a file.",
      "parameters": {
        "type": "object",
        "properties": {
          "content": {
            "type": "string"
          },
          "file_path": {
            "type": "string"
          }
        },
        "additionalProperties": true,
        "required": [
          "content",
          "file_path"
        ]
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "mcp__claude_ai_Gmail__authenticate",
      "description": "Call the claude ai Gmail MCP tool authenticate.",
      "parameters": {
        "type": "object",
        "properties": {
          "code": {
            "type": "string"
          },
          "redirect_uri": {
            "type": "string"
          }
        },
        "additionalProperties": true
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "mcp__claude_ai_Gmail__complete_authentication",
      "description": "Call the claude ai Gmail MCP tool complete authentication.",
      "parameters": {
        "type": "object",
        "properties": {
          "code": {
            "type": "string"
          },
          "redirect_uri": {
            "type": "string"
          }
        },
        "additionalProperties": true
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "mcp__claude_ai_Google_Calendar__authenticate",
      "description": "Call the claude ai Google Calendar MCP tool authenticate.",
      "parameters": {
        "type": "object",
        "properties": {
          "code": {
            "type": "string"
          },
          "redirect_uri": {
            "type": "string"
          }
        },
        "additionalProperties": true
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "mcp__claude_ai_Google_Calendar__complete_authentication",
      "description": "Call the claude ai Google Calendar MCP tool complete authentication.",
      "parameters": {
        "type": "object",
        "properties": {
          "code": {
            "type": "string"
          },
          "redirect_uri": {
            "type": "string"
          }
        },
        "additionalProperties": true
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "mcp__claude_ai_Google_Drive__authenticate",
      "description": "Call the claude ai Google Drive MCP tool authenticate.",
      "parameters": {
        "type": "object",
        "properties": {
          "code": {
            "type": "string"
          },
          "redirect_uri": {
            "type": "string"
          }
        },
        "additionalProperties": true
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "mcp__claude_ai_Google_Drive__complete_authentication",
      "description": "Call the claude ai Google Drive MCP tool complete authentication.",
      "parameters": {
        "type": "object",
        "properties": {
          "code": {
            "type": "string"
          },
          "redirect_uri": {
            "type": "string"
          }
        },
        "additionalProperties": true
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "mcp__context7__query-docs",
      "description": "Call the context7 MCP tool query docs.",
      "parameters": {
        "type": "object",
        "properties": {
          "context7CompatibleLibraryID": {
            "type": "string"
          },
          "tokens": {
            "type": "integer"
          },
          "topic": {
            "type": "string"
          }
        },
        "additionalProperties": true
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "mcp__context7__resolve-library-id",
      "description": "Call the context7 MCP tool resolve library id.",
      "parameters": {
        "type": "object",
        "properties": {
          "libraryName": {
            "type": "string"
          }
        },
        "additionalProperties": true
      }
    }
  }
]
```

</details>