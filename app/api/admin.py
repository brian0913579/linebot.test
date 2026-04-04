from functools import wraps

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from app.models.datastore_client import (
    add_user,
    get_allowed_users,
    get_pending_users,
    log_admin_action,
    remove_pending_user,
    remove_user,
    update_user,
)
from utils.logger_config import get_logger

logger = get_logger(__name__)
admin_bp = Blueprint("admin", __name__)


def check_auth(username, password):
    """Check if a username/password combination is valid."""
    expected_username = current_app.config["ADMIN_USERNAME"]
    expected_password = current_app.config["ADMIN_PASSWORD"]

    if expected_password == "password":
        logger.warning("Using default admin password! Please set ADMIN_PASSWORD.")

    return username == expected_username and password == expected_password


def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("admin.admin_login", next=request.url))
        return f(*args, **kwargs)

    return decorated


@admin_bp.route("/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        if check_auth(username, password):
            session.clear()  # clear any old sessions to avoid session fixation
            session["logged_in"] = True
            session.permanent = (
                True  # Use permanent session (defaults to 31 days in Flask)
            )
            flash("Logged in successfully", "success")
            return redirect(url_for("admin.admin_dashboard"))
        else:
            flash("Invalid credentials", "error")

    return render_template("admin_login.html")


@admin_bp.route("/logout")
def admin_logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("admin.admin_login"))


@admin_bp.route("/", methods=["GET"])
@requires_auth
def admin_dashboard():
    users = get_allowed_users()
    pending_users = get_pending_users()
    return render_template("admin.html", users=users, pending_users=pending_users)


@admin_bp.route("/approve", methods=["POST"])
@requires_auth
def admin_approve():
    user_id = request.form.get("user_id")
    user_name = request.form.get("user_name")

    if user_id and user_name:
        if add_user(user_id, user_name):
            remove_pending_user(user_id)
            log_admin_action(
                admin_username=current_app.config["ADMIN_USERNAME"],
                action="APPROVE_USER",
                target_user_id=user_id,
                metadata={"name": user_name},
            )
            flash(f"Approved: {user_name}", "success")
        else:
            flash("Failed to approve user", "error")
    else:
        flash("Missing user data", "error")

    return redirect(url_for("admin.admin_dashboard"))


@admin_bp.route("/reject", methods=["POST"])
@requires_auth
def admin_reject():
    user_id = request.form.get("user_id")
    if user_id:
        if remove_pending_user(user_id):
            log_admin_action(
                admin_username=current_app.config["ADMIN_USERNAME"],
                action="REJECT_USER",
                target_user_id=user_id,
            )
            flash(f"Rejected: {user_id}", "success")
        else:
            flash("Failed to reject user", "error")

    return redirect(url_for("admin.admin_dashboard"))


@admin_bp.route("/delete", methods=["POST"])
@requires_auth
def admin_delete():
    user_id = request.form.get("user_id")
    if user_id:
        if remove_user(user_id):
            log_admin_action(
                admin_username=current_app.config["ADMIN_USERNAME"],
                action="DELETE_USER",
                target_user_id=user_id,
            )
            flash(f"Deleted: {user_id}", "success")
        else:
            flash("Failed to delete user", "error")

    return redirect(url_for("admin.admin_dashboard"))


@admin_bp.route("/edit_user", methods=["POST"])
@requires_auth
def edit_user():
    user_id = request.form.get("user_id")
    if not user_id:
        flash("Missing user ID", "error")
        return redirect(url_for("admin.admin_dashboard"))

    nickname = request.form.get("nickname", "")
    start_date = request.form.get("start_date", "")
    end_date = request.form.get("end_date", "")
    parking_space = request.form.get("parking_space", "")
    is_admin = request.form.get("is_admin") == "on"
    is_moderator = request.form.get("is_moderator") == "on"

    updates = {
        "nickname": nickname,
        "start_date": start_date,
        "end_date": end_date,
        "parking_space": parking_space,
        "is_admin": is_admin,
        "is_moderator": is_moderator,
    }

    if not is_admin and not is_moderator:
        if "contract_photo" in request.files:
            file = request.files["contract_photo"]
            if file.filename:
                from app.services.storage_service import upload_contract_photo
                url = upload_contract_photo(user_id, file)
                if url:
                    updates["contract_url"] = url

    if update_user(user_id, updates):
        log_admin_action(
            admin_username=current_app.config["ADMIN_USERNAME"],
            action="EDIT_USER",
            target_user_id=user_id,
        )
        flash(f"Updated user: {user_id}", "success")
    else:
        flash("Failed to update user", "error")

    return redirect(url_for("admin.admin_dashboard"))
