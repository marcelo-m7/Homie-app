"""
Bills routes for Homie Flask application
"""
from flask import Blueprint, render_template, request, redirect, url_for, jsonify, session, flash
from authentication import login_required, api_auth_required, feature_required
from database import get_db_connection
from security import csrf_protect, validate_ownership, sanitize_input
from datetime import datetime
from utils.bills_utils import mark_bill_paid, get_budget_analytics, get_spending_history, process_recurring_bills
import logging

logger = logging.getLogger(__name__)

bills_bp = Blueprint('bills', __name__)

@bills_bp.route('/bills')
@login_required
@feature_required('bills')
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
    
    # Calculate monthly total based on recurrence patterns
    monthly_total = 0
    for bill in bills:
        amount = bill['amount']
        recurrence = bill['recurrence_pattern'] if bill['is_recurring'] else 'monthly'
        
        if recurrence == 'weekly':
            # Weekly bills: multiply by 4 for monthly estimate
            monthly_total += amount * 4
        elif recurrence == 'yearly':
            # Yearly bills: divide by 12 for monthly portion (excluded from monthly total)
            monthly_total += amount / 12
        else:  # monthly or non-recurring
            monthly_total += amount
    
    conn.close()
    return render_template('bills.html', bills=bills, monthly_total=monthly_total, categories=categories, view='unpaid')

@bills_bp.route('/bills/paid')
@login_required
@feature_required('bills')
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
    
    # Calculate total paid based on recurrence patterns
    monthly_total = 0
    for bill in bills:
        amount = bill['amount']
        recurrence = bill['recurrence_pattern'] if bill['is_recurring'] else 'monthly'
        
        if recurrence == 'weekly':
            # Weekly bills: multiply by 4 for monthly estimate
            monthly_total += amount * 4
        elif recurrence == 'yearly':
            # Yearly bills: divide by 12 for monthly portion
            monthly_total += amount / 12
        else:  # monthly or non-recurring
            monthly_total += amount
    
    conn.close()
    return render_template('bills.html', bills=bills, monthly_total=monthly_total, categories=categories, view='paid')

@bills_bp.route('/bills/budget')
@login_required
@feature_required('budget')
def budget_dashboard():
    """Display budget analytics dashboard"""
    analytics = get_budget_analytics()
    
    conn = get_db_connection()
    categories = conn.execute('SELECT * FROM budget_categories ORDER BY name').fetchall()
    conn.close()
    
    return render_template('budget.html', analytics=analytics, categories=categories)

@bills_bp.route('/bills/add', methods=['POST'])
@login_required
@feature_required('bills')
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
        
        # Due day is optional now - use 1 as default if not specified
        due_day_str = request.form.get('due_day', '').strip()
        due_day = 1  # Default to 1st of month
        if due_day_str:
            try:
                due_day = int(due_day_str)
                if due_day < 1 or due_day > 31:
                    flash('Due day must be between 1 and 31', 'error')
                    return redirect(url_for('bills.bills_list'))
            except (ValueError, TypeError):
                flash('Invalid due day format', 'error')
                return redirect(url_for('bills.bills_list'))
        
        category = sanitize_input(request.form.get('category', 'Other'))
        
        # Check recurrence pattern to determine if recurring
        recurrence_pattern = request.form.get('recurrence_pattern', '').strip()
        is_recurring = bool(recurrence_pattern)  # True if pattern is set, False if empty
        
        # If not recurring, clear the recurrence pattern
        if not is_recurring:
            recurrence_pattern = None
        
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

@bills_bp.route('/edit_bill', methods=['POST'])
@login_required
@csrf_protect
@feature_required('bills')
def edit_bill():
    """Edit an existing bill via form submission"""
    try:
        bill_id = request.form.get('bill_id')
        bill_name = sanitize_input(request.form.get('bill_name', '').strip())
        amount = request.form.get('amount')
        due_day = request.form.get('due_day')
        
        if not all([bill_id, bill_name, amount, due_day]):
            flash('All fields are required', 'error')
            return redirect(url_for('bills.bills_list'))
        
        try:
            bill_id = int(bill_id)
            amount = float(amount)
            due_day = int(due_day)
        except (ValueError, TypeError):
            flash('Invalid data provided', 'error')
            return redirect(url_for('bills.bills_list'))
        
        if not (1 <= due_day <= 31):
            flash('Due day must be between 1 and 31', 'error')
            return redirect(url_for('bills.bills_list'))
        
        if amount < 0:
            flash('Amount must be positive', 'error')
            return redirect(url_for('bills.bills_list'))
        
        conn = get_db_connection()
        
        # Check if bill exists
        bill = conn.execute('SELECT * FROM bills WHERE id = ?', (bill_id,)).fetchone()
        if not bill:
            conn.close()
            flash('Bill not found', 'error')
            return redirect(url_for('bills.bills_list'))
        
        # Update the bill
        conn.execute('''
            UPDATE bills 
            SET bill_name = ?, amount = ?, due_day = ?
            WHERE id = ?
        ''', (bill_name, amount, due_day, bill_id))
        
        conn.commit()
        conn.close()
        
        user_id = session['user']['id']
        logger.info(f"User {user_id} updated bill {bill_id}")
        flash('Bill updated successfully', 'success')
        return redirect(url_for('bills.bills_list'))
        
    except Exception as e:
        logger.error(f"Error updating bill: {e}")
        flash('Failed to update bill', 'error')
        return redirect(url_for('bills.bills_list'))

@bills_bp.route('/api/bills/pay/<int:bill_id>', methods=['POST'])
@api_auth_required
@csrf_protect
@feature_required('bills')
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
@feature_required('bills')
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
@feature_required('bills')
def delete_bill_api(bill_id):
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
@feature_required('budget')
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
@feature_required('budget')
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

@bills_bp.route('/api/categories', methods=['POST'])
@api_auth_required
@csrf_protect
def add_category():
    """Add a new bill category"""
    try:
        data = request.get_json()
        if not data or 'name' not in data:
            return jsonify({'error': 'Category name is required'}), 400
        
        name = sanitize_input(data['name'])
        if not name:
            return jsonify({'error': 'Category name cannot be empty'}), 400
        
        monthly_limit = float(data.get('monthly_limit', 0))
        if monthly_limit < 0:
            return jsonify({'error': 'Monthly limit cannot be negative'}), 400
        
        conn = get_db_connection()
        
        # Check if category already exists
        existing = conn.execute('SELECT id FROM budget_categories WHERE name = ?', (name,)).fetchone()
        if existing:
            conn.close()
            return jsonify({'error': 'Category already exists'}), 400
        
        conn.execute('''
            INSERT INTO budget_categories (name, monthly_limit)
            VALUES (?, ?)
        ''', (name, monthly_limit))
        
        conn.commit()
        conn.close()
        
        logger.info(f"User {session['user']['id']} added category: {name}")
        return jsonify({'success': True, 'message': 'Category added successfully'})
        
    except Exception as e:
        logger.error(f"Error adding category: {e}")
        return jsonify({'error': 'Failed to add category'}), 500

@bills_bp.route('/api/categories/<int:category_id>', methods=['PUT'])
@api_auth_required
@csrf_protect
@feature_required('budget')
def update_category(category_id):
    """Edit a bill category name"""
    try:
        data = request.get_json()
        if not data or 'name' not in data:
            return jsonify({'error': 'Category name is required'}), 400
        
        name = sanitize_input(data['name'])
        if not name:
            return jsonify({'error': 'Category name cannot be empty'}), 400
        
        conn = get_db_connection()
        
        # Check if new name already exists (excluding current category)
        existing = conn.execute(
            'SELECT id FROM budget_categories WHERE name = ? AND id != ?',
            (name, category_id)
        ).fetchone()
        if existing:
            conn.close()
            return jsonify({'error': 'Category name already exists'}), 400
        
        # Get old name for updating bills
        old_category = conn.execute('SELECT name FROM budget_categories WHERE id = ?', (category_id,)).fetchone()
        if not old_category:
            conn.close()
            return jsonify({'error': 'Category not found'}), 404
        
        # Update category name
        conn.execute('UPDATE budget_categories SET name = ? WHERE id = ?', (name, category_id))
        
        # Update all bills with this category
        conn.execute('UPDATE bills SET category = ? WHERE category = ?', (name, old_category['name']))
        
        conn.commit()
        conn.close()
        
        logger.info(f"User {session['user']['id']} edited category {category_id} to: {name}")
        return jsonify({'success': True, 'message': 'Category updated successfully'})
        
    except Exception as e:
        logger.error(f"Error editing category: {e}")
        return jsonify({'error': 'Failed to edit category'}), 500

@bills_bp.route('/api/categories/<int:category_id>', methods=['DELETE'])
@api_auth_required
@csrf_protect
@feature_required('budget')
def delete_category(category_id):
    """Delete a bill category"""
    try:
        conn = get_db_connection()
        
        # Check if category is in use
        bills_using = conn.execute('SELECT COUNT(*) as count FROM bills WHERE category = (SELECT name FROM budget_categories WHERE id = ?)', (category_id,)).fetchone()
        
        if bills_using['count'] > 0:
            conn.close()
            return jsonify({'error': f'Cannot delete category. {bills_using["count"]} bill(s) are using it.'}), 400
        
        result = conn.execute('DELETE FROM budget_categories WHERE id = ?', (category_id,))
        
        if result.rowcount == 0:
            conn.close()
            return jsonify({'error': 'Category not found'}), 404
        
        conn.commit()
        conn.close()
        
        logger.info(f"User {session['user']['id']} deleted category {category_id}")
        return jsonify({'success': True, 'message': 'Category deleted successfully'})
        
    except Exception as e:
        logger.error(f"Error deleting category: {e}")
        return jsonify({'error': 'Failed to delete category'}), 500