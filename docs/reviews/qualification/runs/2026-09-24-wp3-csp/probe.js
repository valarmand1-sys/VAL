const out = document.getElementById("out");
      const lines = [];
      const say = (text) => {
        lines.push(text);
        out.textContent = lines.join("\n");
        console.log(text);
      };
      async function probe() {
        say("policy: " + document.querySelector("meta[http-equiv]")?.content ?? "(header only)");
        const context = new AudioContext();

        // 1. The way work package 3 first loaded its processor: a blob: URL.
        const source = "class P extends AudioWorkletProcessor{process(){return true}}registerProcessor('blob-probe',P);";
        const blobUrl = URL.createObjectURL(new Blob([source], { type: "text/javascript" }));
        say("BLOB URL: " + blobUrl);
        try {
          await context.audioWorklet.addModule(blobUrl);
          say("BLOB RESULT: loaded (no CSP refusal)");
        } catch (failure) {
          say("BLOB RESULT: REFUSED — " + failure.name + ": " + failure.message);
        }

        // 2. The fix: the same processor, served from the application itself.
        try {
          await context.audioWorklet.addModule("/pcm-worklet.js");
          say("SAME-ORIGIN RESULT: loaded");
        } catch (failure) {
          say("SAME-ORIGIN RESULT: REFUSED — " + failure.name + ": " + failure.message);
        }
      }
      probe();
