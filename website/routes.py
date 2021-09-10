import bcrypt,datetime,random
from bs4 import BeautifulSoup
from flask import render_template,url_for,flash,redirect,request,send_from_directory,session,abort
from website.forms import (RegistrationForm,LoginForm,ResetPasswordForm,AccountForm,
                            NewTaskForm,ResetRequestForm,SubmitTaskForm,FeedbackForm,
                            FilterForm,AnnouncementForm,MeetupForm,MeetupInfoForm)
from website.models import (User,Task,Submit,Announce,Meetup,Meetup_Info,Excuses,Missed,
                            Notifications,Notifications_Settings,Email_Settings,Department)
from website import app,db

from flask_login import login_user,current_user,logout_user,login_required
from website.functions import days,save_file,noti_text,mail_sender,url_extractor

permissions={
    'task_creators':['IEEE Chairman','Vice Technical',"RAS Chairman",'RAS Vice Chairman',"Team Leader"],
    'task_submitters':["Team Member","Rookie"],
    'announcers':['IEEE Chairman','Vice Technical',"RAS Chairman",'RAS Vice Chairman']  
}


def noti_clearer(noti):
    if noti != 0:
        Notifications.query.get(noti).clicked = True
        db.session.commit()

def noti_fetcher():
    notifications = Notifications.query.filter_by(to_id = current_user.id).order_by(Notifications.date.desc())
    return notifications

@app.errorhandler(404)
def not_found(_):
    flash("Sorry, the page you trying to acess does not exist",'danger')
    return render_template('layout.html',notifications =noti_fetcher())

@app.errorhandler(403)
def no_permission(_):
    flash("You do not have permission to access this page",'danger')
    return render_template('layout.html',notifications=noti_fetcher())

@app.route("/about",methods= ['GET','POST'])
@login_required
def about():
    if current_user.is_authenticated:
        notifications=noti_fetcher()
    else:
        notifications = None
    return render_template('about.html',title = 'About',sidebar=True,notifications=notifications)

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('home'))

@app.route('/due/<department>')
@login_required
def due(department):
    if current_user.position in permissions['task_creators']:
        tasks = Task.query.filter(Task.author == current_user).order_by(Task.date_posted.desc())
        tasks = tasks.paginate(per_page = 3)
    else:
        tasks = Task.query.filter(Task.deadline >= datetime.datetime.today() ,Task.department == current_user.department).order_by(Task.date_posted.desc())
        tasks = tasks.paginate(per_page = 3)
    return render_template('home.html',tasks = tasks,due = True,len = len,days =days,permissions=permissions,
        route = 'due',Submit = Submit,notifications=noti_fetcher(),sidebar=True)


@app.route('/profile/<username>',methods=['GET','POST'])
@login_required
def profile(username):

    to_view = User.query.filter_by(username = username).first()
    return render_template('profile.html',to_view = to_view,sidebar=True,
        title = ' '.join([to_view.first_name,to_view.last_name]),len = len,notifications=noti_fetcher())

@app.route('/<path:location>/<filename>')
def get_file(location,filename):
    try:
        return send_from_directory(location,filename,as_attachment =False)
    except FileNotFoundError:
        abort(404)

def get_user(MyForm):
    if '@' in MyForm.username_email.data and User.query.filter_by(email = MyForm.username_email.data):
        return User.query.filter_by(email = MyForm.username_email.data).first()
    elif User.query.filter_by(username = MyForm.username_email.data).first():
        return User.query.filter_by(username = MyForm.username_email.data).first()

@app.route('/<department>')
@login_required
def department(department):
    leaders = User.query.filter(User.department == department,User.position.in_(permissions['task_creators']))
    members = User.query.filter(User.department == department,User.position.in_(permissions['task_submitters']))
    to_display= Department.query.filter_by(department=department).first()
   
    return render_template('department.html',leaders = leaders,notifications=noti_fetcher(),
        members = members, len =len,dep =to_display)

@app.route('/task/<department>/<int:task_id>/submits',methods= ['GET','POST'])
@login_required
def submits(department,task_id):
    form = FeedbackForm()
    return render_template('submits.html',days= days,
        location = app.config['SUBMITS_FILE'],notifications=noti_fetcher(),
        task = Task.query.get(task_id),permissions=permissions,
        submits = Submit.query.filter_by(task_id = task_id).order_by(Submit.date_submitted.desc()).paginate(per_page = 3))

@app.route("/",defaults={'sort':'Date Posted','method':'asc','dep':None},methods= ['GET','POST'])
@app.route("/home",defaults={'sort':'Date Posted','method':'asc','dep':None},methods= ['GET','POST'])
@app.route("/home/<dep>/<sort>/<method>",methods= ['GET','POST'])
@login_required
def home(sort,method,dep):
    if current_user.is_authenticated:
        notifications=noti_fetcher()
    else:
        notifications = None

    filter_form = FilterForm()
    new_form = NewTaskForm()

    if filter_form.validate_on_submit() and filter_form.filter.data:
        dep,sort,method =filter_form.department.data,filter_form.sort.data,filter_form.method.data

    elif new_form.validate_on_submit() and new_form.submit.data:

        new_form.content = url_extractor(new_form.content)

        new_task = Task(author = current_user ,title = new_form.title.data, content= new_form.content.data, 
            deadline = new_form.deadline.data,file = save_file(new_form.file.data,app.config['TASKS_FILE']),
            department = current_user.department,submits_count = 0)
        db.session.add(new_task)
        db.session.commit()

        type,text,route = noti_text('task',position='Team Member',name=current_user.last_name,
                date=days(new_task.deadline,state='abs'))

        recipients=[]
        for user in User.query.filter(User.department == new_task.department , User.position.not_in(permissions['task_creators'])):
            
            if user.noti_settings.first().task:
                noti = Notifications(type =type, data = text,route = route,data_id = new_task.id,
                                     to_id= user.id,sender = current_user)
                misser = Missed(misser = user,task = new_task)
                db.session.add(user)
                db.session.add(noti)
                db.session.commit()

            if user.email_settings.first().task:
                recipients.append(user.email)

        mail_sender(recipients=recipients,content='tech',type=type,text=text)
        Department.query.filter_by(department=new_task.department).first().tasks += 1

        db.session.commit()
        flash("Task created successfully",'success')
        return redirect(url_for('home'))
    else:
        task=Task.query.order_by(Task.date_posted.desc())
        
    if dep:
        task=Task.query.filter_by(department=dep)

    if sort == 'Date Posted' and method =='asc':
        task = task.order_by(Task.date_posted.asc()).paginate(per_page = 3)
    elif sort == 'Title' and method =='asc':
        task = task.order_by(Task.title.asc()).paginate(per_page = 3)
    elif sort =='Deadline' and method =='asc':
        task = task.order_by(Task.deadline.asc()).paginate(per_page = 3)
    elif sort =='Submits Count' and method == 'asc':
        task = task.order_by(Task.submits_count.asc()).paginate(per_page = 3)            
    elif sort == 'Date Posted' and method =='desc':
        task = task.order_by(Task.date_posted.desc()).paginate(per_page = 3)            
    elif sort == 'Title' and method =='desc':
        task = task.order_by(Task.title.desc()).paginate(per_page = 3)
    elif sort =='Deadline' and method =='desc':
        task = task.order_by(Task.deadline.desc()).paginate(per_page = 3)
    elif sort =='Submits Count' and method == 'desc':
        task = task.order_by(Task.submits_count.desc()).paginate(per_page = 3)
    
    if request.method =='GET':
        filter_form.sort.data=sort
        filter_form.method.data=method
        filter_form.department.data =dep

    return render_template('home.html',tasks =task,Submit = Submit,permissions=permissions,
     due = False,sidebar =True, notifications=notifications,
     days = days,filter_form =filter_form,form = new_form,location=app.config['TASKS_FILE'],
     len = len,route = 'home',sort=sort,method=method,dep=dep)

@app.route("/register",methods=['GET','POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('home'))

    form = RegistrationForm()
    if form.validate_on_submit():
        if form.department.data=='Select a Department':
            form.department.data='All'
        subscriber = User(first_name = form.first_name.data.capitalize().strip(), 
                     last_name = form.last_name.data.capitalize().strip(),
                     username = form.username.data.strip(), email = form.email.data.strip(),
                     password = bcrypt.hashpw(form.password.data.encode('utf-8'),bcrypt.gensalt()),
                     department = form.department.data, position = form.position.data,
                     birthdate = form.birthdate.data,age = int(days(form.birthdate.data)/365))
        db.session.add(subscriber)
        noti_setting= Notifications_Settings(user= subscriber)
        db.session.add(noti_setting)
        email_settings= Email_Settings(user= subscriber)
        db.session.add(email_settings)
        db.session.commit()
        if not Department.query.filter_by(department = form.department.data).first():
            dep =Department(department = form.department.data)
            db.session.add(dep)
            db.session.commit()
        flash(f'Account created successfully for {form.first_name.data.capitalize()} {form.last_name.data.capitalize()}','success')
        login_user(User.query.filter_by(email= form.email.data).first())
        return redirect(url_for('home'))   
    return render_template('register.html',title= 'Register',form = form)
    
@app.route("/login",methods=['GET','POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
        
    form = LoginForm()
    if form.validate_on_submit():
        loginer = get_user(form)
        if loginer:
            if bcrypt.checkpw(form.password.data.encode('utf-8'), loginer.password):
                flash('Login in successfully','success')
                login_user(loginer,remember =form.remember.data)
                next_page = request.args.get('next')
                return redirect(next_page) if next_page is not None else redirect(url_for('home'))
            else:
                flash('Incorrect email or password','danger')
        else:
            flash("This user is not registered",'danger')
    return render_template('login.html',title= 'Login',form = form)

@app.route('/reset_request/<int:state>',methods=['GET','POST'])
def reset_request(state):
    if current_user.is_authenticated:
        return redirect(url_for('home'))

    if state ==1:
        form = ResetRequestForm()
        if form.validate_on_submit():
            flash('An email has been sent with a reset code','success')
            resetter = User.query.filter_by(email = form.email.data).first()
            session['sent'] =  mail_sender([resetter.email])
            session['id'] = resetter.id
            return redirect(url_for('reset_request',state= 0))
    else:
        form = ResetPasswordForm()
        if form.validate_on_submit():
            if int(form.code.data) == session.get('sent',None):
                resetter = User.query.get(session.get('id',None))
                resetter.password = bcrypt.hashpw(form.password.data.encode('utf-8'),bcrypt.gensalt())
                login_user(resetter)
                db.session.commit()
                flash('Changes have been saved','success')
                return redirect(url_for('home'))
            else:
                flash('Invalid or expired code','danger')
    return render_template('reset_request.html',title = 'Reset',form = form,state = state)

@app.route('/account',methods=['GET','POST'])
@login_required
def account():
    noti_fetcher()
    form = AccountForm()
    image_file = url_for('static',filename='profile_pics/' + current_user.image_file)
    if request.method == 'POST':
        if request.form.get('Delete') =='Delete My Account!':
            to_delete = User.query.filter_by(email = current_user.email).first()
            db.session.delete(to_delete)
            db.session.commit()
            return redirect(url_for('logout'))
        elif form.validate_on_submit():
            if form.profile_photo.data:
                current_user.image_file = save_file(form.profile_photo.data,app.config['PROFILE_PICS'])

            current_user.first_name = form.first_name.data
            current_user.last_name = form.last_name.data
            
            c = current_user.noti_settings.first()
            c.review =form.noti_review.data
            c.task =form.noti_task.data
            c.submit =form.noti_submit.data
            c.announcement =form.noti_announcement.data
            c.meetup =form.noti_meetup.data
            c.missed =form.noti_missed.data
            c.excuse =form.noti_excuse.data

            e = current_user.email_settings.first()
            e.review =form.email_review.data
            e.task =form.email_task.data
            e.submit =form.email_submit.data
            e.announcement =form.email_announcement.data
            e.meetup =form.email_meetup.data
            e.missed =form.email_missed.data
            e.excuse =form.email_excuse.data

            if current_user.username != form.username.data:
                current_user.username = form.username.data
            if current_user.email != form.email.data:
                current_user.email = form.email.data
            if len(form.password.data) >2 :
                current_user.password= bcrypt.hashpw(form.password.data.encode('utf-8'),bcrypt.gensalt())
            # if current_user.department != form.department.data:
            #     current_user.department = form.department.data
            # if current_user.position != form.position.data:
            #     current_user.position = form.position.data

            db.session.commit()
            flash(f'Changes have been saved','success')
            return(redirect(url_for('account')))
        else:
            flash('Some of the inputs are invalid, recheck your data','danger')
    elif request.method == 'GET':
        u=current_user
        u_n =u.noti_settings.first()
        u_e =u.email_settings.first()
        form.username.data=u.username
        form.email.data = u.email
        form.first_name.data = u.first_name
        form.last_name.data = u.last_name
        form.department.data=u.department
        form.position.data = u.position
        form.noti_task.data=u_n.task
        form.noti_review.data=u_n.review
        form.noti_submit.data=u_n.submit
        form.noti_excuse.data=u_n.excuse
        form.noti_missed.data=u_n.missed
        form.noti_announcement.data=u_n.announcement
        form.noti_meetup.data=u_n.meetup
        form.email_task.data=u_e.task
        form.email_review.data=u_e.review
        form.email_submit.data=u_e.submit
        form.email_excuse.data=u_e.excuse
        form.email_missed.data=u_e.missed
        form.email_announcement.data=u_e.announcement
        form.email_meetup.data=u_e.meetup

    return render_template('account.html',title = 'Account',form = form, image_file = image_file,permissions=permissions,
        sidebar=True,notifications=noti_fetcher())

@app.route('/task/<department>/<int:id>-<int:noti>',methods= ['GET','POST'])
@login_required
def view_task(department,id,noti):
    noti_fetcher()
    noti_clearer(noti)
    submit_form = SubmitTaskForm()
    new_form = NewTaskForm()
    Excuseform = MeetupInfoForm()

    task = Task.query.get(id)
    submits = Submit.query.filter_by(task_id = id).order_by(Submit.date_submitted.desc())
    submit = submits.filter_by(user_id = current_user.id).first()
    excuses = Excuses.query.filter_by(task_id = id)
    excuse= excuses.filter_by(user_id =current_user.id).first()
    missed = Missed.query.filter_by(task_id = id)
    
    if not task:
        abort(404)
    elif new_form.validate_on_submit() and new_form.submit.data:

        new_form.content = url_extractor(new_form.content)

        task.title = new_form.title.data
        task.content= new_form.content.data
        task.deadline = new_form.deadline.data
        if new_form.file.data is not None : 
            task.file =save_file(new_form.file.data,app.config['TASKS_FILE'])
        db.session.commit()
        flash("Changes have been saved",'success')
        return redirect(url_for('view_task',department = department,id =id,days = days,noti=0))

    elif submit_form.validate_on_submit() and submit_form.submit.data:

        new_submit = Submit(submitter = current_user,task = task, notes = submit_form.notes.data,
            file = save_file(submit_form.file.data,app.config['SUBMITS_FILE']))
        task.submits_count += 1

        recipients=[]
        type,text,route = noti_text('submit',position='Team Leader',name=current_user.last_name,task=task.title)
        for user in User.query.filter(User.department == task.department , User.position.in_(permissions['task_creators'])):

            if user.noti_settings.first().submit:
                noti = Notifications(type =type, data = text,route = route,data_id = new_submit.id,task=task,
                                     to_id= user.id,sender = current_user)
                db.session.add(noti)
    
            if user.email_settings.first().submit:
                recipients.append(user.email)

        mail_sender(recipients=recipients,content='tech',type=type,text=text)
        db.session.add(new_submit)
        db.session.commit()
        missed = Missed.query.filter_by(user_id = current_user.id,task_id = id).first()
        if missed:
            db.session.delete(missed)
        Department.query.filter_by(department=task.department).first().submits += 1
        db.session.commit()
        flash("Your submit has been saved",'success')
        return redirect(url_for('view_task',department = department,id =id,noti=0))

    elif Excuseform.validate_on_submit() and Excuseform.save.data:
        excuse = Excuses(notes = Excuseform.notes.data,excuser =current_user,task= task)

        recipients=[]
        type,text,route = noti_text('excuse',position='Team Leader',name=current_user.last_name,task=task.title)
        for user in User.query.filter(User.department == task.department , User.position.in_(permissions['task_creators'])):
            if user.noti_settings.first().excuse:
                noti = Notifications(type =type, data = text,route = route,data_id = id,
                                     to_id= user.id,sender = current_user)
                db.session.add(noti)
        
            if user.email_settings.first().excuse:
                recipients.append(user.email)

        mail_sender(recipients=recipients,content='tech',type=type,text=text)

        db.session.add(excuse)
        missed = Missed.query.filter_by(user_id = current_user.id,task_id = id).first()
        if missed:
            db.session.delete(missed)
        Department.query.filter_by(department=task.department).first().excuses += 1
        db.session.commit()
        flash("You have been excused",'warning')
        return(redirect(url_for('view_task',department = department,id =id,noti=0)))

    elif request.method == 'GET':
        content = BeautifulSoup(task.content)
        new_form.title.data = task.title
        new_form.content.data =content.get_text()
        new_form.file.data = task.file
        new_form.deadline.data = task.deadline

    if request.method == 'POST':
        if request.form.get('Delete')=='Delete':
            db.session.delete(task)
            Notifications.query.filter_by(type='task',data_id = id).delete(synchronize_session=False)
            db.session.commit()
            return redirect(url_for('home'))

    if task.deadline < datetime.datetime.today():
        type,text,route = noti_text('missed',position='Team Member',task = task.title)

        if not Notifications.query.filter_by(type=type,data_id=id).first():
            recipients=[]
            for miss in task.missed:
                noti = Notifications(type =type, data = text,route = route,data_id = id,task=task,
                                     to_id= miss.user_id,sender = current_user)
                db.session.add(noti)
                if miss.misser.email_settings.first().missed:
                    recipients.append(miss.misser.email)

            db.session.commit()     
            mail_sender(recipients=recipients,content='tech',type=type,text=text)
            
    return render_template('task.html',title = task.title,task = task,new_form=new_form,missed = missed,permissions=permissions
        ,submit_form = submit_form,Excuseform = Excuseform,excuses =excuses,excuse= excuse,notifications=noti_fetcher()
        ,location=app.config['TASKS_FILE'],days = days,submit = submit,submits= submits,
        len = len,datetime = datetime)

@app.route('/task/<department>/<int:id>/submits/<int:submit_id>-<int:noti>',methods= ['GET','POST'])
@login_required
def view_submit(department,id,submit_id,noti):
    noti_fetcher()
    noti_clearer(noti)
    task = Task.query.get(id)
    submit = Submit.query.get(submit_id)
    form = FeedbackForm()

    if form.validate_on_submit():
        submit.feedback = form.feedback.data
        submit.score = form.score.data
        submit.submitter.score += int(form.score.data)
        current_user.score += int(form.score.data)

        if submit.submitter.noti_settings.first().review:
            type,text,route = noti_text('review',position='Team Member',name=current_user.last_name,task= submit.task.title)
            noti = Notifications(type =type, data = text,route = route,data_id = id,
                                 to_id= submit.submitter.id,sender = current_user)
            db.session.add(noti)

        if submit.submitter.noti_settings.first().review:
            recipients=[submit.submitter.email]
            mail_sender(recipients=recipients,content='tech',type=type,text=text)

        db.session.commit()
        flash('Your feedback has been delivered','success')
        return redirect(url_for('submits',task_id = id,department = department))

    return render_template('submit.html',submit= submit,days = days,permissions=permissions,
        location=app.config['SUBMITS_FILE'],task = task,form = form,notifications=noti_fetcher())

@app.route('/announcements/<department>/<int:id>-<int:noti>',methods =['POST','GET'])
@login_required
def announcements(department,id,noti):
    noti_fetcher()
    noti_clearer(noti)
    form = AnnouncementForm()

    if form.validate_on_submit():
        if form.department.data =='Select a department' or not form.department.data:
            form.department.data=current_user.department

        announcement = Announce(content = form.content.data,validation_date = form.validation_date.data,
            announcer=current_user,department = form.department.data)
        db.session.add(announcement)

        recipients=[]
        type,text,route = noti_text('announcement',name=current_user.last_name,date=days(form.validation_date.data,state='abs'))
        if announcement.department =='All':
            for user in User.query.filter(User.id !=current_user.id ):
                if user.noti_settings.first().announcement:
                    noti = Notifications(type =type, data = text,route = route,data_id = 0,
                                         to_id= user.id,sender = current_user)
                    db.session.add(noti)
                if user.email_settings.first().announcement:
                    recipients.append(user.email)
        else:
            for user in User.query.filter(((User.department == announcement.department) |( User.department=='All')), User.id != current_user.id):
                if user.noti_settings.first().announcement:
                    noti = Notifications(type =type, data = text,route = route,data_id = 0,
                                         to_id= user.id,sender = current_user)
                    db.session.add(noti)
                if user.email_settings.first().announcement:
                    recipients.append(user.email)
            Department.query.filter_by(department=announcement.department).first().announcements += 1

        db.session.commit()
        mail_sender(recipients=recipients,content='tech',type=type,text=text)
        flash('Announcement created successfully','success')
        return redirect(url_for('announcements',department = current_user.department,id =0,noti= 0))
    else:
        if id != 0:
            db.session.delete(Announce.query.get(id))
            db.session.commit()

    return render_template('announcements.html',form =form,sidebar=True,notifications=noti_fetcher(),permissions=permissions,
        announcements = Announce.query.order_by(Announce.date_announced.desc()).paginate(per_page = 5))

@app.route('/meetups',methods =['POST','GET'])
@login_required
def meetups():
    form = MeetupForm()
    if form.validate_on_submit():
        if form.department.data =='Select a department' or not form.department.data:
            form.department.data=current_user.department

        date =datetime.datetime(form.date.data.year,form.date.data.month,form.date.data.day,
            form.time.data.hour,form.time.data.minute,form.time.data.second)

        meetup = Meetup(title = form.title.data,date = date,about = form.about.data,state=form.state.data,
            organizer = current_user,department = form.department.data,long = form.long.data,
            lat = form.lat.data)
        db.session.add(meetup)
        db.session.commit()

        type,text,route = noti_text('meetup',name=current_user.last_name,
                date=days(meetup.date,state='abs'),status=form.state.data)
        
        recipients=[]
        if meetup.department =='All':
            for user in User.query.filter(User.id != current_user.id):
                if user.noti_settings.first().meetup:
                    noti = Notifications(type =type, data = text,route = route,data_id = meetup.id,
                                         to_id= user.id,sender = current_user)
                    db.session.add(noti)

                if user.email_settings.first().meetup:
                    recipients.append(user.email)
        else:
            for user in User.query.filter(((User.department == meetup.department) |( User.department=='All')), User.id != current_user.id):
                if user.noti_settings.first().meetup:
                    noti = Notifications(type =type, data = text,route = route,data_id = meetup.id,
                                         to_id= user.id,sender = current_user)
                    db.session.add(noti)

                if user.email_settings.first().meetup:
                    recipients.append(user.email)
            Department.query.filter_by(department=current_user.department).first().meetups += 1

        mail_sender(recipients=recipients,content='tech',type=type,text=text)
        db.session.commit()
        flash('Meet-up created successfully','success')
    return render_template('meet-ups.html',form =form,sidebar= True,notifications=noti_fetcher(),permissions=permissions,
        meetups = Meetup.query.order_by(Meetup.date_created.desc()).paginate(per_page = 5))

@app.route('/meetups/<department>/<int:id>-<int:noti>',methods=['POST','GET'])
@login_required
def meetup(department,id,noti):
    noti_clearer(noti)
    # queries
    meetup = Meetup.query.get(id)
    if not meetup:
        abort(404)
    excuses = [info for info in meetup.info if info.type == 'excuse']
    confirms = [info for info in meetup.info if info.type == 'confirm']
    user_info = Meetup_Info.query.filter_by(meetup_id = id, user_id=current_user.id).first()
    # end of queries
    Excuseform = MeetupInfoForm()

    if request.form.get('Delete')=='Delete':
        db.session.delete(meetup)

        """
            Child objects can be deleted upon the deletion of their parents IF THERE IS A RELATIONSHIP 
            and cascade option is set to all/delete but in this case, there is no relationship established as
            I still don't know how to generate a dynamic FORIEGN KEYS.
        """
        Notifications.query.filter_by(type='meetup',data_id = id).delete(synchronize_session=False)
        ''''''
        db.session.commit()
        flash('Meet-up deleted successfully','success')
        return redirect(url_for('meetups'))

    elif request.form.get('Confirm') == 'Confirm your attendence':
        info = Meetup_Info(type ='confirm',caser=current_user,meetup_id = meetup.id)
        db.session.add(info)
        flash("Your attendence has been confirmed",'success')
        db.session.commit()
        return(redirect(url_for('meetup',department = department,id =id,noti=0)))

    elif Excuseform.validate_on_submit():
        info = Meetup_Info(type ='excuse', notes = Excuseform.notes.data,caser=current_user,meetup_id = meetup.id)
        db.session.add(info)
        flash("You have been excused",'warning')
        db.session.commit()
        return(redirect(url_for('meetup',department = department,id =id,noti=0)))
        
    return render_template('meetup.html',meetup = meetup,Excuseform = Excuseform,notifications=noti_fetcher(),
        excuses = excuses,confirms =confirms,user_info = user_info,len=len,permissions= permissions)

@app.route('/notifications/<int:user_id>/read?<int:mark_as_read>')
@login_required
def notifications(user_id,mark_as_read):
    if user_id == current_user.id:
        if mark_as_read:
            for noti in Notifications.query.filter_by(to_id =user_id,clicked=False):
                noti.clicked=True
            db.session.commit()
            flash('All unread notifications have been marked as read','success')
        notifications = Notifications.query.filter_by(to_id =user_id).paginate(per_page=15)
    else:
        abort(403)
    return render_template('notifications.html',notifications_paginated=notifications,notifications=None)
