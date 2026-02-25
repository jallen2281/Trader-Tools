"""
Authentication Module
Phase 2: Google OAuth Integration
"""

import os
import json
from flask import session, redirect, request, url_for
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from authlib.integrations.flask_client import OAuth
from datetime import datetime, timedelta
import secrets

from models import db, User, UserSession
from db_config import get_or_create_user

# Initialize OAuth
oauth = OAuth()

def init_auth(app):
    """Initialize authentication system"""
    
    # Configure Flask-Login
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'login'
    
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))
    
    # Configure OAuth
    oauth.init_app(app)
    
    google = oauth.register(
        name='google',
        client_id=app.config['GOOGLE_CLIENT_ID'],
        client_secret=app.config['GOOGLE_CLIENT_SECRET'],
        server_metadata_url=app.config['GOOGLE_DISCOVERY_URL'],
        client_kwargs={
            'scope': 'openid email profile'
        }
    )
    
    return login_manager, google


def create_session_token(user_id):
    """Create a new session token for user"""
    token = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(days=30)
    
    session_obj = UserSession(
        user_id=user_id,
        session_token=token,
        expires_at=expires_at
    )
    
    db.session.add(session_obj)
    db.session.commit()
    
    return token


def verify_session_token(token):
    """Verify session token and return user"""
    session_obj = UserSession.query.filter_by(session_token=token).first()
    
    if not session_obj or session_obj.is_expired():
        return None
    
    # Update last activity
    session_obj.last_activity = datetime.utcnow()
    db.session.commit()
    
    return User.query.get(session_obj.user_id)


def get_auth_routes(google):
    """Return authentication route handlers"""
    
    def login():
        """Initiate Google OAuth login"""
        if current_user.is_authenticated:
            return redirect(url_for('dashboard'))
        
        redirect_uri = url_for('authorize', _external=True)
        return google.authorize_redirect(redirect_uri)
    
    def authorize():
        """Handle Google OAuth callback"""
        token = google.authorize_access_token()
        user_info = token.get('userinfo')
        
        if user_info:
            # Create or update user
            user = get_or_create_user(
                google_id=user_info['sub'],
                email=user_info['email'],
                name=user_info.get('name', ''),
                picture_url=user_info.get('picture', '')
            )
            
            # Log user in
            login_user(user)
            
            # Create session token
            session_token = create_session_token(user.id)
            session['token'] = session_token
            
            return redirect(url_for('dashboard'))
        
        return redirect(url_for('index'))
    
    def logout_route():
        """Log out current user"""
        if current_user.is_authenticated:
            # Invalidate session token
            token = session.get('token')
            if token:
                session_obj = UserSession.query.filter_by(session_token=token).first()
                if session_obj:
                    db.session.delete(session_obj)
                    db.session.commit()
            
            logout_user()
            session.clear()
        
        return redirect(url_for('index'))
    
    return {
        'login': login,
        'authorize': authorize,
        'logout': logout_route
    }


def require_api_auth(f):
    """Decorator for API endpoints that require authentication"""
    def decorated_function(*args, **kwargs):
        # Check session token
        token = request.headers.get('Authorization')
        if token and token.startswith('Bearer '):
            token = token[7:]  # Remove 'Bearer ' prefix
            user = verify_session_token(token)
            if user:
                # Attach user to request for API access
                request.current_user = user
                return f(*args, **kwargs)
        
        # Check if user is logged in via Flask-Login
        if current_user.is_authenticated:
            request.current_user = current_user
            return f(*args, **kwargs)
        
        return {'error': 'Authentication required'}, 401
    
    decorated_function.__name__ = f.__name__
    return decorated_function
