🫁 ThoraxGPT from Wish

A very good friend of mine had a CT of his chest taken last week. And then he had his images. And no medical evaluation.

So I said: Come, let's get this done at home and prepare an app where we can evaluate ourselves the scans. The ideas was simple: let's figure out what existing models and tools from the public domain can be used to evaluate those images and detect issues. As well as: how to run them and what quirks are known. After realizing that several ones are not just ML models, but LLMs, the path with local hosting via #Ollama was clear: who would like to see their most intimate data in the cloud?

A bit of Python for the backend, a bit of HTML and CSS for the front, tons of ollama-models and several iterations later to understand what the models actually return, jobs for queued works, polishing, done.

😂 I have to admit, if it was this easy, I would have finished this "oh, this should not take long" project way earlier. Several assumptions were wrong, outcomes of random sampling of the CT-scans were not good, model quality was  ... let's say most are overconfident at praising what they can do - so I added also a pre-rating for each of them. Since I am no doctor - the user is still free to override this. My recommendation is "monai_lung_nodule" as model. Another obstacle was to find good medical data, since I wanted to keep the data to analyse separate from the "development data". Then: does it make sense to prepare synthetic data (..not) and why is DICOM a standard, when there are some deviations in the medial data.

Nevertheless: all is solved now. The app works and gives human-readable results.
There is still no evaluation from an expert, but based on the app I prepared I would say: his data looks good, nothing really to worry about.

So, mission done.

GitHub -> marcelpetrick -> ThoraxGPT_from_Wish
https://github.com/marcelpetrick/ThoraxGPT_from_Wish
