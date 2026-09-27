async function runCode(){

    let code=document.getElementById("editor").value;

    let response=await fetch("/api/run/",{

        method:"POST",

        headers:{
            "Content-Type":"application/json",
            "X-CSRFToken":getCookie("csrftoken")
        },

        body:JSON.stringify({

            code:code

        })

    });

    let data=await response.json();

    document.getElementById("output").textContent=data.stdout;

    document.getElementById("error").textContent=data.stderr;

}

function getCookie(name){

    let cookieValue=null;

    if(document.cookie && document.cookie!==""){

        const cookies=document.cookie.split(";");

        for(let cookie of cookies){

            cookie=cookie.trim();

            if(cookie.startsWith(name+"=")){

                cookieValue=decodeURIComponent(cookie.substring(name.length+1));

                break;

            }

        }

    }

    return cookieValue;

}