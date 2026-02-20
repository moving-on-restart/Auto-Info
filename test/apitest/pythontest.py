from openai import OpenAI

client = OpenAI(
  base_url="https://aihubmix.com/v1",
  api_key="sk-niHUW338MXE0bVFzEf5fF477B712407eAb28EdA488012953",
)

completion = client.chat.completions.create(
  model="claude-opus-4-5-think",
  messages=[
    {
      "role": "assistant",
      "content": "总是用中文回复"
    },
    {
      "role": "user",
      "content": "What is the meaning of life?"
    }
  ]
)

print(completion.choices[0].message.content)