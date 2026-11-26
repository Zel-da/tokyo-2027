// index.html 에서 C(좌표)와 ROUTES(경로)를 꺼내 JSON으로 출력
const fs=require("fs");
const s=fs.readFileSync(process.argv[2],"utf8");
const grab=(name)=>{const a=s.indexOf("const "+name+"={");let i=s.indexOf("{",a),d=0;for(let j=i;j<s.length;j++){if(s[j]=="{")d++;else if(s[j]=="}"){d--;if(!d)return s.slice(i,j+1);}}};
const C=eval("("+grab("C")+")"), ROUTES=eval("("+grab("ROUTES")+")");
process.stdout.write(JSON.stringify({C,ROUTES}));
