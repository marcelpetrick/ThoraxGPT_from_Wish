🫁 𝐓𝐡𝐨𝐫𝐚𝐱𝐆𝐏𝐓 𝐟𝐫𝐨𝐦 𝐖𝐢𝐬𝐡

A very good friend of mine had a CT of his chest taken last week. And then he had his images. And no medical evaluation.

So I said: Come, let's get this done at home and prepare an app where 𝐰𝐞 𝐜𝐚𝐧 𝐞𝐯𝐚𝐥𝐮𝐚𝐭𝐞 𝐭𝐡𝐞 𝐬𝐜𝐚𝐧𝐬 𝐨𝐮𝐫𝐬𝐞𝐥𝐯𝐞𝐬. The idea was simple: let's figure out what existing models and tools from the public domain can be used to evaluate those images and detect issues. As well as: how to run them and what quirks are known. After realizing that several of them are not just ML models, but LLMs, the path with local hosting via #Ollama was clear: who would like to see their most intimate data in the cloud?

A bit of #Python for the backend, a bit of HTML and CSS for the front, tons of Ollama models and several iterations later to understand what the models actually return, jobs for queuing work, polishing, done.

😂 I have to admit, if it was this easy, I would have finished this "oh, this should not take long" project way earlier. Several assumptions were wrong, outcomes from random sampling of the CT scans were not good, model quality was ... let's say most are overconfident when praising what they can do - so I also added a pre-rating for each of them. Since I am no doctor - the user is still free to override this. My recommendation is "𝐦𝐨𝐧𝐚𝐢_𝐥𝐮𝐧𝐠_𝐧𝐨𝐝𝐮𝐥𝐞" as a model. Another obstacle was finding good medical data, since I wanted to keep the data to analyse separate from the "development data". Then: does it make sense to prepare synthetic data (...not) and why is #DICOM a standard when there are some deviations in the medical data?

Nevertheless: all is solved now. The app works and gives human-readable results.
There is still no evaluation from an expert, but based on the app I prepared, I would say: 𝐡𝐢𝐬 𝐝𝐚𝐭𝐚 𝐥𝐨𝐨𝐤𝐬 𝐠𝐨𝐨𝐝, 𝐧𝐨𝐭𝐡𝐢𝐧𝐠 𝐫𝐞𝐚𝐥𝐥𝐲 𝐭𝐨 𝐰𝐨𝐫𝐫𝐲 𝐚𝐛𝐨𝐮𝐭. This is, of course, not a medical diagnosis.

So, mission done.

𝐆𝐢𝐭𝐇𝐮𝐛 -> 𝐦𝐚𝐫𝐜𝐞𝐥𝐩𝐞𝐭𝐫𝐢𝐜𝐤 -> 𝐓𝐡𝐨𝐫𝐚𝐱𝐆𝐏𝐓_𝐟𝐫𝐨𝐦_𝐖𝐢𝐬𝐡
https://github.com/marcelpetrick/ThoraxGPT_from_Wish
