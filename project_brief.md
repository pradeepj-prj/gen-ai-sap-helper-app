Hey Claude Opus, 

Here is my initial though for this project. Currently this project is a Gen AI implementation using SAP Gen AI hub that does a very specific task of classifying the user's query as either a talent management related query or not. For more
details on the implementation and overview you can check out the CLAUDE.md file. You will also find some files related to Joule skills as I was trying to get SAP Joule to call this API and perform some actions. That will be unrelated to this project, so later on you can go ahead and delete the joule skills portion. For this project, the plan is to convert this Gen AI API into something more real and useful. I want to create an API that provides the user with REAL 
SAP documentation links depending on the user's query and context of the question. The job of the LLM will be to intelligently reason about the user's question and provide the right links for the user to review. The user might ask things like the following: 

Example: "Where can I find more information about AI core?" 
Example: "What are the sources of to do document grounding with SAP Gen AI hub?" 
Example: "How do I set up Joule skills?"
Example: "How does RAG work in the SAP ecosystem?" 
Example: "What are the different capabilities for HANA cloud?" 

These are questions where the user needs additional documentation help. So the Gen AI tool has to find the relevant links to provide back to the user. On top of that, the model should also provide some basic response to the user so that they
may already have a simple, bare bones answer of what they are asking. This tool will be used internally, published to Cloud Foundry in our team's BTP subaccount, and different team members will mainly ask it documentation related questions about SAP AI. 

Now I am open to already providing some useful links for a start. Since the information is scattered across many different places - and it is more useful to provide very detailed links that brings the user to exactly the right place rather than the 
simple soltion of just redirecting them to SAP Help and then they type in the service they are looking for instead. In that case, there is no need for this tool. 

I am thinking it may also be helpful to maybe scrap the website? Maybe a tool that the LLM can use to scrap a particular website? I need your help to determine if there is a good idea. Keep in mind that documentation website usually have many tabs 
in the sidebar, so you can let me know if that is too complicated an idea and maybe left to a future implementation. 

I am also yet unsure if GenAI hub would have access in general to the internet, but I have a strong feeling that is not the case. Personal LLMs are able to search the internet in thinking mode and so on, but I don't know if that would be 
allowed in a Gen AI Hub SAP implementation, the tool use idea is something to consider if we want to get around that. If the tool use works that the Gen AI model, rather than just giving the links can actually give the user a direct but 
detailed answer, on top of providing the links. 

There are certain features of this project that I wish to keep: 
- FastAPI implementation framework 
- Use of Gen AI hub SDK 
- Using the same credentials, saving in .env environment (which should already be done) and using dotenv 
- Pushing to cloud foundry 
- Keeping certain guardrails in place like: content filtering, data masking 
- I also want to keep the optional return of the pipeline process: azure filtering scores, original prompt, masked prompt 

Later on (for another project), I want to build an LLM input/output analyzer to show what exactly happens when we use the GenAI Hub SDK. 

That is the main project brief. Can you please come up with a plan, and ask important/pertinent clarifying questions that will lead to a reliable and successful implementation of this API. Feel free to brainstorm with me on what needs to be 
done. I want this to be collaborative and you can ask as many questions and implementation options to consider.  
