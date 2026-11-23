const fs=require('node:fs');fs.mkdirSync('dist',{recursive:true});for(const f of ['index.html','app.js','style.css'])fs.copyFileSync(f,'dist/'+f);console.log('Static demo built');
