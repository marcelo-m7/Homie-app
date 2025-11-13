"""
Bills routes for Homie Flask application
"""
from flask import Blueprint, render_template, request, redirect, url_for, jsonify, session, flash
from authentication import login_required, api_auth_required
from database import get_db_connection
from security import csrf_protect, validate_ownership, sanitize_input
from datetime import datetime
from utils.bills_utils import mark_bill_paid, get_budget_analytics, get_spending_history, process_recurring_bills
import logging

logger = logging.getLogger(__name__)

bills_bp = Blueprint('bills', __name__)

@bills_bp.route('/bills')
@login_required
def bills_list():
    """Display the bills page - unpaid bills"""
    # Process any recurring bills that need renewal
    try:
        process_recurring_bills()
    except Exception as e:
        logger.error(f"Error processing recurring bills: {e}")
    
    conn = get_db_connection()
    
    # Get all unpaid bills
    bills = conn.execute('''
        SELECT b.*, u.username as added_by_name
        FROM bills b
        LEFT JOIN users u ON b.added_by = u.id
        WHERE b.is_paid = FALSE
        ORDER BY b.due_day ASC, b.created_at DESC
    ''').fetchall()
    
    # Get budget categories
    categories = conn.execute('SELECT name FROM budget_categories ORDER BY name').fetchall()
    
    # Calculate monthly total
    monthly_total = conn.execute('''
        SELECT SUM(amount) as total FROM bills WHERE is_paid = FALSE
    ''').fetchone()['total'] or 0
    
    conn.close()
    return render_template('bills.html', bills=bills, monthly_total=monthly_total, categories=categories, view='unpaid')

@bills_bp.route('/bills/paid')
@login_required
def paid_bills_list():
    """Display all paid bills"""
    conn = get_db_connection()
    
    # Get all paid bills with paid_by user info
    bills = conn.execute('''
        SELECT b.*, 
               u1.username as added_by_name,
               u2.username as paid_by_name
        FROM bills b
        LEFT JOIN users u1 ON b.added_by = u1.id
        LEFT JOIN users u2 ON b.paid_by = u2.id
        WHERE b.is_paid = TRUE
        ORDER BY b.paid_date DESC, b.created_at DESC
    ''').fetchall()
    
    # Get budget categories
    categories = conn.execute('SELECT name FROM budget_categories ORDER BY name').fetchall()
    
    # Calculate total paid
    monthly_total = conn.execute('''
        SELECT SUM(amount) as total FROM bills WHERE is_paid = TRUE
    ''').fetchone()['total'] or 0
    
    conn.close()
    return render_template('bills.html', bills=bills, monthly_total=monthly_total, categories=categories, view='paid')

@bills_bp.route('/bills/budget')
@login_required
def budget_dashboard():
    """Display budget analytics dashboard"""
    from datetime import datetime
    
    analytics = get_budget_analytics()
    history = get_spending_history(months=6)
    
    conn = get_db_connection()
    categories = conn.execute('SELECT * FROM budget_categories ORDER BY name').fetchall()
    conn.close()
    
    now = datetime.now()
    current_month = now.strftime('%Y-%m')
    current_month_name = now.strftime('%B %Y')
    
    return render_template('budget.html', 
                         analytics=analytics, 
                         history=history, 
                         categories=categories,
                         current_month=current_month,
                         current_month_name=current_month_name)

@bills_bp.route('/bills/add', methods=['POST'])
@login_required
def add_bill():
    """Add a new bill via form submission"""
    try:
        bill_name = sanitize_input(request.form.get('bill_name', '').strip())
        if not bill_name:
            flash('Bill name is required', 'error')
            return redirect(url_for('bills.bills_list'))
        
        try:
            amount = float(request.form.get('amount', '0'))
            if amount < 0:
                flash('Amount cannot be negative', 'error')
                return redirect(url_for('bills.bills_list'))
        except (ValueError, TypeError):
            flash('Invalid amount format', 'error')
            return redirect(url_for('bills.bills_list'))
        
        try:
            due_day = int(request.form.get('due_day', '1'))
            if due_day < 1 or due_day > 31:
                flash('Due day must be between 1 and 31', 'error')
                return redirect(url_for('bills.bills_list'))
        except (ValueError, TypeError):
            flash('Invalid due day format', 'error')
            return redirect(url_for('bills.bills_list'))
        
        category = sanitize_input(request.form.get('category', 'Other'))
        is_recurring = request.form.get('is_recurring') == 'on'
        recurrence_pattern = request.form.get('recurrence_pattern', 'monthly')
        
        user_id = session['user']['id']
        
        conn = get_db_connection()
        conn.execute('''
            INSERT INTO bills (bill_name, amount, due_day, category, is_recurring, recurrence_pattern, added_by)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (bill_name, amount, due_day, category, is_recurring, recurrence_pattern, user_id))
        conn.commit()
        conn.close()
        
        logger.info(f"User {user_id} added bill: {bill_name}")
        flash('Bill added successfully', 'success')
        return redirect(url_for('bills.bills_list'))
        
    except Exception as e:
        logger.error(f"Error adding bill: {e}")
        flash('Failed to add bill', 'error')
        return redirect(url_for('bills.bills_list'))

@bills_bp.route('/api/bills/pay/<int:bill_id>', methods=['POST'])
@api_auth_required
@csrf_protect
def pay_bill(bill_id):
    """Mark a bill as paid"""
    try:
        user_id = session['user']['id']
        success = mark_bill_paid(bill_id, user_id)
        
        if success:
            return jsonify({'success': True, 'message': 'Bill marked as paid'})
        else:
            return jsonify({'error': 'Failed to mark bill as paid'}), 500
            
    except Exception as e:
        logger.error(f"Error marking bill as paid: {e}")
        return jsonify({'error': 'Failed to process payment'}), 500

@bills_bp.route('/api/bills/add', methods=['POST'])
@api_auth_required
@csrf_protect
def add_bill_api():
    """Add a new bill via API"""
    try:
        data = request.get_json()
        if not data or 'bill_name' not in data or 'amount' not in data or 'due_day' not in data:
            return jsonify({'error': 'Bill name, amount, and due day are required'}), 400
        
        bill_name = sanitize_input(data['bill_name'].strip())
        if not bill_name:
            return jsonify({'error': 'Bill name cannot be empty'}), 400
        
        try:
            amount = float(data['amount'])
            if amount < 0:
                return jsonify({'error': 'Amount cannot be negative'}), 400
        except (ValueError, TypeError):
            return jsonify({'error': 'Invalid amount format'}), 400
        
        try:
            due_day = int(data['due_day'])
            if due_day < 1 or due_day > 31:
                return jsonify({'error': 'Due day must be between 1 and 31'}), 400
        except (ValueError, TypeError):
            return jsonify({'error': 'Invalid due day format'}), 400
        
        user_id = session['user']['id']
        
        category = sanitize_input(data.get('category', 'Other'))
        is_recurring = data.get('is_recurring', False)
        recurrence_pattern = data.get('recurrence_pattern', 'monthly')
        
        conn = get_db_connection()
        conn.execute('''
            INSERT INTO bills (bill_name, amount, due_day, category, is_recurring, recurrence_pattern, added_by)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (bill_name, amount, due_day, category, is_recurring, recurrence_pattern, user_id))
        conn.commit()
        conn.close()
        
        logger.info(f"User {user_id} added bill: {bill_name}")
        return jsonify({'success': True, 'message': 'Bill added successfully'})
        
    except Exception as e:
        logger.error(f"Error adding bill: {e}")
        return jsonify({'error': 'Failed to add bill'}), 500

@bills_bp.route('/api/bills/delete/<int:bill_id>', methods=['DELETE'])
@api_auth_required
@csrf_protect
def delete_bill(bill_id):
    """Delete a bill"""
    try:
        conn = get_db_connection()
        
        # Validate ownership or admin rights
        if not validate_ownership(conn, 'bills', bill_id, session['user']):
            conn.close()
            return jsonify({'error': 'Unauthorized'}), 403
        
        # Delete the bill
        result = conn.execute('DELETE FROM bills WHERE id = ?', (bill_id,))
        
        if result.rowcount == 0:
            conn.close()
            return jsonify({'error': 'Bill not found'}), 404
        
        conn.commit()
        conn.close()
        
        user_id = session['user']['id']
        logger.info(f"User {user_id} deleted bill {bill_id}")
        
        return jsonify({'success': True, 'message': 'Bill deleted successfully'})
        
    except Exception as e:
        logger.error(f"Error deleting bill {bill_id}: {e}")
        return jsonify({'error': 'Failed to delete bill'}), 500

@bills_bp.route('/api/budget/categories', methods=['GET'])
@api_auth_required
def get_budget_categories():
    """Get all budget categories"""
    try:
        conn = get_db_connection()
        categories = conn.execute('SELECT * FROM budget_categories ORDER BY name').fetchall()
        conn.close()
        
        return jsonify({'categories': [dict(cat) for cat in categories]})
        
    except Exception as e:
        logger.error(f"Error fetching budget categories: {e}")
        return jsonify({'error': 'Failed to fetch categories'}), 500

@bills_bp.route('/api/budget/categories/<int:category_id>', methods=['PUT'])
@api_auth_required
@csrf_protect
def update_budget_category(category_id):
    """Update a budget category limit"""
    try:
        data = request.get_json()
        if not data or 'monthly_limit' not in data:
            return jsonify({'error': 'Monthly limit is required'}), 400
        
        try:
            monthly_limit = float(data['monthly_limit'])
            if monthly_limit < 0:
                return jsonify({'error': 'Monthly limit cannot be negative'}), 400
        except (ValueError, TypeError):
            return jsonify({'error': 'Invalid monthly limit format'}), 400
        
        conn = get_db_connection()
        result = conn.execute('''
            UPDATE budget_categories 
            SET monthly_limit = ?
            WHERE id = ?
        ''', (monthly_limit, category_id))
        
        if result.rowcount == 0:
            conn.close()
            return jsonify({'error': 'Category not found'}), 404
        
        conn.commit()
        conn.close()
        
        logger.info(f"User {session['user']['id']} updated budget category {category_id}")
        return jsonify({'success': True, 'message': 'Category updated successfully'})
        
    except Exception as e:
        logger.error(f"Error updating budget category: {e}")
        return jsonify({'error': 'Failed to update category'}), 500