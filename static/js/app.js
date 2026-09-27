const sidebar = document.getElementById("sidebar");

const menu = document.getElementById("menu-btn");

menu.onclick = function(){

sidebar.classList.toggle("hide");

}


const notices=[

"📢 Thi giữa kỳ Java sẽ diễn ra ngày 20/08.",

"📢 Thi cuối kỳ C++ sẽ mở lúc 8h00.",

"📢 Sinh viên kiểm tra lịch thi trước khi làm bài.",

"📢 Chúc các bạn đạt kết quả tốt."

];

let current=0;

setInterval(()=>{

const text=document.getElementById("noticeText");

if(text){

current++;

if(current>=notices.length){

current=0;

}

text.innerHTML=notices[current];

}

},3500);


window.addEventListener("scroll",()=>{

const cards=document.querySelectorAll(".question-card");

cards.forEach((card,index)=>{

const top=card.getBoundingClientRect().top;

const number=document.getElementById("number"+(index+1));

if(top<200 && top>-200){

number.classList.add("current");

}else{

number.classList.remove("current");

}

});

});
document

.querySelectorAll(

"input"

)

.forEach(i=>{

i.onchange=()=>{

localStorage.setItem(

i.name,

i.value

);

};

});
window.onload=()=>{

document

.querySelectorAll("input")

.forEach(i=>{

if(

localStorage.getItem(i.name)

==i.value

){

i.checked=true;

}

});

}