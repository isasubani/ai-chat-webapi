curl -X POST http://localhost:3001/v1/chat/completions      -H "Content-Type: application/json"      -H "Authorization: Bearer dummy-key"      -d '{
           "messages": [
             {
               "role": "user",
               "content": "Halo, siapa kamu? Jawab dengan singkat dan ramah."
             }
           ],
           "model": "gemini-web"
         }'
