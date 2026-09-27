let time=duration;

let time = duration;

const timer = document.getElementById("timer");

function updateTimer(){

    const hour=Math.floor(time/3600);

    const minute=Math.floor((time%3600)/60);

    const second=time%60;

    timer.innerHTML=

        hour.toString().padStart(2,'0')

        +":"

        +minute.toString().padStart(2,'0')

        +":"

        +second.toString().padStart(2,'0');

    if(time<=0){

        alert("Hết giờ!");

        document.querySelector("form").submit();

    }

    time--;

}

setInterval(updateTimer,1000);

function scrollQuestion(number){

document

.getElementById(

"question"+number

)

.scrollIntoView({

behavior:"smooth"

});

}

const radios=document.querySelectorAll("input[type=radio]");

radios.forEach(r=>{

r.addEventListener("change",()=>{

const question=

r.name.replace("q","");

const card=r.closest(".question-card");

const number=Array.from(document.querySelectorAll(".question-card")).indexOf(card)+1;

document

.getElementById("number"+number)

.classList.add("answered");

});

});